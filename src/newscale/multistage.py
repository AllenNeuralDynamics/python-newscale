"""Abstractions for many stages grouped together."""

import logging
from functools import wraps
from newscale.stage import M3LinearSmartStage
from newscale.device_codes import StateBit, Direction, Mode, DriveMode, \
    parse_stage_reply
from newscale.interfaces import USBInterface
from typing import Tuple, Optional
from time import perf_counter, sleep


# Decorators
def axis_check(*args_to_skip: str):
    """Ensure that the axis (specified as an arg or kwarg) exists."""
    def wrap(func):
        # wraps needed for sphinx to make docs for methods with this decorator.
        @wraps(func)
        def inner(self, *args, **kwargs):
            # Sanitize input to all-lowercase.
            args = [a.lower() for a in args]
            kwargs = {k.lower(): v for k, v in kwargs.items()}
            # Combine args and kwarg names; skip double-adding params specified
            # as one or the other.
            iterable = [a for a in args if a not in kwargs] + \
                       list(kwargs.keys())
            for arg in iterable:
                # Skip pre-specified args.
                if arg in args_to_skip:
                    continue
                assert arg.lower() in self.stages, \
                    f"Error. Axis '{arg.lower()}' does not exist"
            return func(self, *args, **kwargs)
        return inner
    return wrap


class MultiStage:
    """A conglomerate of many stages from many interfaces."""
    MOVE_TIMEOUT_S = 15.0

    def __init__(self, **stages: M3LinearSmartStage):
        """Init a MultiStage object from one or more stages.

        :param stages: one or more stage objects keyed by name.

        .. code-block:: python

            from newscale.interfaces import USBInterface
            from newscale.stage import M3LinearSmartStage
            from newscale.multistage import MultiStage

            interface = USBInterface(port='COM4'),
            x_stage = M3LinearSmartStage(interface, "01")
            y_stage = M3LinearSmartStage(interface, "02")

            stages = MultiStage(x=x_stage, y=y_stage)

        """
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        # Sanitize input to lowercase.
        self.stages = {k.lower(): v for k, v in stages.items()}

    @axis_check()
    def _set_drive_mode(self, drive_mode: DriveMode):
        """Set all axes to the specified modes.

        :param drive_mode: drive mode specified as
            :attr:`~newscale.device_codes.DriveMode.OPEN_LOOP` or
            :attr:`~newscale.device_codes.DriveMode.CLOSED_LOOP`.
        """
        for _, axis in self.stages.items():
            axis.set_drive_mode(drive_mode)

    def set_open_loop_mode(self):
        """Set all axes to open loop mode."""
        axes_dict = {x: DriveMode.OPEN_LOOP for x in self.stages.keys()}
        self._set_drive_mode(**axes_dict)

    def set_closed_loop_mode(self):
        """Set all axes to closed loop mode."""
        axes_dict = {x: DriveMode.CLOSED_LOOP for x in self.stages.keys()}
        self._set_drive_mode(**axes_dict)

    @axis_check('wait')
    def move_absolute(self, wait: bool = True, **axes: float):
        """Move the specified axes by the specified amounts.

        Note: the multistage will `not` travel in a straight line to its
        destination unless accelerations and speeds are set to do so.

        Note: issuing absolute moves requires that the stage first be in
        closed loop mode.

        :param wait: bool indicating if this function should block until the
            stage has reached its destination.
        :param axes: one or more axes specified by name with their move amount
            specified in [mm].

        .. code-block:: python

            stages.move_absolute(x=5, y=7.5, z=10) # move x, y, and z
            stages.move_absolute(x=7.5, wait=False)  # move x only. Don't wait.

        """
        for axis_name, abs_position_mm in axes.items():
            self.stages[axis_name].move_to_target(abs_position_mm)
        if not wait:
            return
        # Poll position vector until we have reached the target or timeout.
        start_time = perf_counter()
        while perf_counter() - start_time < self.__class__.MOVE_TIMEOUT_S:
            stats = {x: self.stages[x].get_closed_loop_state_and_position()[0]
                     for x in axes.keys()}
            if any([stats[x][StateBit.STALLED] for x in axes.keys()]):
                raise RuntimeError("One or more axes is stalled.")
            if all([(not stats[x][StateBit.RUNNING])
                    and stats[x][StateBit.ON_TARGET]
                    for x in axes.keys()]):
                return
            sleep(0.01)
        raise RuntimeError("Axes timed out trying to reach target position.")

    @axis_check('wait')
    def move_for_time(self, wait: bool = True,
                      **axes: Tuple[Direction, Optional[float]]):
        """Move axes specified for the corresponding amount of time in seconds.

        Note: the multistage will `not` travel in a straight line to its
            destination unless accelerations and speeds are set to do so.

        :param wait: bool indicating if this function should block until the
            stage has reached its destination.
        :param axes: a per-axis tuple of
            ``(Direction, <move_time_in_seconds>)``.
            the move time can be set to None, and the axis will run until
            reaching a limit or being issued a halt.
        """
        for axis_name, (direction, seconds) in axes.items():
            self.stages[axis_name].run(direction, seconds)
        if not wait:
            return
        # Poll position vector until we have reached the target or timeout.
        start_time = perf_counter()
        while perf_counter() - start_time < self.__class__.MOVE_TIMEOUT_S:
            stats = {x: self.stages[x].get_closed_loop_state_and_position()[0]
                     for x in axes.keys()}
            if any([stats[x][StateBit.STALLED] for x in axes.keys()]):
                raise RuntimeError("One or more axes is stalled.")
            if all([(not stats[x][StateBit.RUNNING])
                    and (not stats[x][StateBit.TIMED_RUN])
                    for x in axes.keys()]):
                return
            sleep(0.01)
        raise RuntimeError("One or more axes timed out trying to move for the"
                           "specified time.")

    @axis_check()
    def get_position(self, *axes: str):
        """Retrieve the specified axes positions (or all if none are specified)
        in [mm] as a dict.

        :param axes: an unlimited number of axes specified by name (string).
        :return: a dict, keyed by axis, of the position per axis in [mm].

        .. code-block:: python

            stages.get_position()  # Get all positions OR
            stages.get_position('x', 'y', 'z')  # Get specified axis positions.

        """
        if not axes:  # Populate all axes if none are specified.
            axes = self.stages.keys()
        return {x: self.stages[x].get_position() for x in axes}

    @axis_check('global_speed')
    def set_open_loop_speed(self, global_speed: float = None, **axes: float):
        """Set the speeds of the specified axes (or all) as a percent.


        :param global_speed: the speed to set all axes
        :param axes: the speed to set to the specified axes.

         .. code-block:: python

            stages.set_open_loop_speed(50.)  # Set all axes to 50% speed.
            stages.set_open_loop_speed(x=50., y=100.)  # Set x axis to 50%; y axis to 100%.

        """
        if global_speed is not None:
            for _, axis in self.stages.items():
                axis.set_open_loop_speed(global_speed)
        else:
            for axis_name, speed in axes.items():
                self.stages[axis_name].set_open_loop_speed(speed)

    @axis_check()
    def get_open_loop_speed(self, *axes: str):
        """Get the speeds of the specified axes (or all if none are specified)
        as a percent.

        :return: a dict, keyed by axis, of the speed setting per axis.

        .. code-block:: python

            stages.get_open_loop_speed('x', 'z')

        """
        if not axes:  # Populate all axes if none are specified.
            axes = self.stages.keys()
        return {x: self.stages[x].get_open_loop_speed() for x in axes}

    @axis_check('global_setting')
    def set_closed_loop_speed_and_accel(self,
            global_setting: Tuple[float, float, Optional[int]] = None,
            **axes: Tuple[float, float, Optional[int]]):
        """Set the speed and accel settings of the specified axes (or all)
        as a tuple.

        :param global_setting: Optional. If specified, the settings will apply
            to all axes. a 2-or-3-tuple of
            ``(<speed in [mm/s]>, <accel in [mm/s^2]>,
            <min speed in [mm/s]>)``.
            Note that ``min speed`` is optional.
        :param axes: a per-axis 2-or-3-tuple of
            ``(<speed in [mm/s]>, <accel in [mm/s^2]>,
            <min speed in [mm/s]>)``.  Note that ``min speed`` is optional.

        .. code-block:: python

            # Set all stage speed/accel values as such:
            stages.set_closed_loop_speed_and_accel((10, 100))
            # Set unique values per stage:
            stages.set_closed_loop_speed_and_accel(x=(10, 100),
                                                   y=(10, 100, 0.1)) # specify a min speed for y.

        """
        if global_setting is not None:
            for _, axis in self.stages.items():
                axis.set_set_closed_loop_speed_and_accel(*global_setting)
        else:
            for name, settings in axes.items():
                self.stages[name].set_closed_loop_speed_and_accel(*settings)

    @axis_check()
    def get_closed_loop_speed_and_accel(self, *axes):
        """Get the speed and accel settings of the specified axes (or all
        if none are specifed) as a dict.

        :return: a dict of 4-tuples, keyed by axis, of the settings per
            specified axis. 4-tuples contain: ``(<speed in [mm/s]>,
            <minimum speed in [mm/s]>, <acceleration in [mm/s^2]>,
            <interval count>)``

        .. code-block:: python

            stages.get_closed_loop_speed_and_accel('x', 'y', 'z')  # Get specific axes.
            stages.get_closed_loop_speed_and_accel()  # Get all xes.

        """
        if not axes:  # Populate all axes if none are specified.
            axes = self.stages.keys()
        return {x: self.stages[x].get_closed_loop_speed_and_accel()
                for x in axes}

    @axis_check()
    def halt(self):
        """Halt all axes"""
        return {x: self.stages[x].halt() for x in self.stages.keys()}

    @axis_check()
    def set_soft_limits(self, **axes: Tuple[float, float, Optional[float]]):
        """set the soft limits per axis.

        :param: dict, keyed by axis, of 2-or-3-tuples representing
            ``(<min limit>, <max limit>, <Optional error margin>)`` in [mm].

        .. code-block:: python

            stages.set_soft_limits(x=(-0.25, 9.75, 0.001),  # set x limits with error margin
                                   y=(0, 3.0))  # set y limits without error margin

        """
        for axis_name, (min_limit, max_limit) in axes.items():
            self.stages[axis_name].set_soft_limits(min_limit, max_limit)

    @axis_check()
    def get_soft_limits(self, *axes):
        """Retrieve the soft limits for specified axes (or all if none are
        specified).

        :return: a dict, keyed by axis name, of 3-tuples representing:
            ``(<min limit>, <max limit>, <error margin>)`` in [mm].
        """
        if not axes:  # Populate all axes if none are specified.
            axes = self.stages.keys()
        return {x: self.stages[x].get_soft_limits() for x in axes}

    def enable_soft_limits(self):
        """Enable software travel limits on all axes."""
        for _, axis in self.stages.items():
            axis.enable_soft_limits()

    def disable_soft_limits(self):
        """Disable software travel limits on all axes."""
        for _, axis in self.stages.items():
            axis.disable_soft_limits()

    def close(self):
        """Release computer control of all axes."""
        return {x: self.stages[x].close() for x in self.stages.keys()}

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class USBXYZStage(MultiStage):
    """An XYZ Stage from a single USB interface."""

    def __init__(self, port: str = None, baud_rate: int = 250000,
                 usb_interface: USBInterface = None):
        """Create a USBXYZStage object on a port and baud rate (if specified),
        or create from an existing interface.

        Note: ``port`` xor ``usb_interface`` can be specified. (i.e: one or
        the other, but not both.)

        :param port: if specified, the port at which to create a USB interface
        :param baud_rate: if specified the particular baud rate to use for the
            port.
        :param usb_interface: an existing usb interface

        .. code-block:: python

            from newscale.multistage import USBXYZStage
            from newscale.interfaces import USBInterface

            # Interface created internally.
            multistage = USBXYZStage('COM4')

            # Interface created internally at a specified baud rate (rare).
            multistage = USBXYZStage('COM4', 115200)

            # Create interface separately and pass it in.
            interface = USBInterface('COM4')
            multistage = USBXYZStage(usb_interface=interface)

        """
        if not ((port is None) ^ (usb_interface is None)):
            raise SyntaxError("Exclusively either port or usb_interface"
                              "(i.e: one or the other, but not both) options "
                              "must be specified.")
        self.interface = usb_interface if usb_interface and not port \
            else USBInterface(port, baud_rate)
        # Create 3 stages with corresponding addresses.
        stages = {'x': M3LinearSmartStage(self.interface, '01'),
                  'y': M3LinearSmartStage(self.interface, '02'),
                  'z': M3LinearSmartStage(self.interface, '03')}
        super().__init__(**stages)
