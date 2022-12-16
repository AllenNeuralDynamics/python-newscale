#!/usr/bin/env python
"""usbxpress.py

Python wrapper for SiUSBXp.dll. Works with Python 2.x and 3.x.

Uses the 32-bit version of SiUSBXp.dll to ensure it works on 32-bit and 
64-bit Windows machine. Does not work on any non-Windows OS.

"""
import ctypes
import logging
import os
import sys

USBXPRESS_RETURN_CODES = \
{
    0x00: "SI_SUCCESS",
    0xFF: "SI_DEVICE_NOT_FOUND",
    0x01: "SI_INVALID_HANDLE",
    0x02: "SI_READ_ERROR",
    0x03: "SI_RX_QUEUE_NOT_READY",
    0x04: "SI_WRITE_ERROR",
    0x05: "SI_RESET_ERROR",
    0x06: "SI_INVALID_PARAMETER",
    0x07: "SI_INVALID_REQUEST_LENGTH",
    0x08: "SI_DEVICE_IO_FAILED",
    0x09: "SI_INVALID_BAUDRATE",
    0x0A: "SI_FUNCTION_NOT_SUPPORTED",
    0x0B: "SI_GLOBAL_DATA_ERROR",
    0x0C: "SI_SYSTEM_ERROR_CODE",
    0x0D: "SI_READ_TIMED_OUT",
    0x0E: "SI_WRITE_TIMED_OUT",
    0x0F: "SI_IO_PENDING",
    0xA0: "SI_NOTHING_TO_CANCEL"
}

class USBXpressException(IOError):
    """Base class for USBXpress-related exceptions."""
    def __init__(self, message, value):
        self.message = message
        self.value = value
        print(message)
    
    def __str__(self):
        print(": %s" % self.message)
        
class USBXpressTimeoutException(IOError):
    """Base class for USBXpress timeout exceptions."""
    def __init__(self, message):
        self.message = message
    
def usbxpress_errcheck(result, func, args):
    """
    Checks return status codes from USBXpress DLL functions and raises an 
    exception if an error occurred.
    """
    if result != 0:
        if result == 0x0D or result == 0x0E:
            raise USBXpressTimeoutException("USBXpress operation timed out")
        else:
            raise USBXpressException("USBXpress runtime error: %r" % \
                                      USBXPRESS_RETURN_CODES.get( \
                                        result, "SI_UNKNOWN_ERROR_CODE"),
                                     result)

#: Maximum string length (affects memory allocation)
MAX_STRING_LENGTH = 4096

#: GetProductString() function flags
PRODUCT_STRING_OPTIONS = \
{
    0x00: "SI_RETURN_SERIAL_NUMBER",
    0x01: "SI_RETURN_DESCRIPTION",
    0x02: "SI_RETURN_LINK_NAME",
    0x03: "SI_RETURN_VID",
    0x04: "SI_RETURN_PID"
}

#: RX Queue status flags
RX_FLAGS = \
{
    0x00: "SI_RX_EMPTY",
    0x01: "SI_RX_OVERRUN",
    0x02: "SI_RX_READY"
}

#: Buffer size limits
BUFFER_LIMITS = \
{
    256: "SI_MAX_DEVICE_STRLEN",
    4096*16: "SI_MAX_READ_SIZE",
    4096: "SI_MAX_WRITE_SIZE"
}

class USBXpressLib(object):
    """
    This class is a wrapper around the USBXpress DLL (SiUSBXp.dll).
    
    Class methods:
    __init__ -- class constructor
    SI_GetNumDevices -- returns the number of attached USBXpress devices
    SI_GetProductString -- returns the product string of a USBXpress device
    SI_GetDLLVersion -- returns the version of the USBXpress DLL in use
    SI_GetDriverVersion -- returns the version of the USBXpress driver in use
    """
    def __init__(self):
        """ Class constructor. """
        # Get DLL from the directory where the USBXpress Installer puts it.
        if os.name == 'nt':
            self._dll = ctypes.WinDLL("C:\\SiliconLabs\\MCU\\USBXpress_SDK\\Library\\Host\\Windows\\x64\\SiUSBXp.dll")
        else:
            raise OSError("USBXpress wrapper not implemented for os %r" % os.name)
        
        # Set the return type and error checking attributes for each function.
        for usbxpress_function in [
            "SI_GetNumDevices", 
            "SI_GetProductString",
            "SI_Open", 
            "SI_Close",
            "SI_Read",
            "SI_Write",
            "SI_CancelIo",
            "SI_FlushBuffers",
            "SI_SetTimeouts",
            "SI_GetTimeouts",
            "SI_CheckRXQueue",
            "SI_SetBaudRate",
            "SI_SetLineControl",
            "SI_SetFlowControl",
            "SI_GetModemStatus",
            "SI_SetBreak",
            "SI_ReadLatch",
            "SI_WriteLatch",
            "SI_GetPartNumber",
            "SI_GetPartLibraryVersion",
            "SI_DeviceIOControl",
            "SI_GetDLLVersion",
            "SI_GetDriverVersion",
            ]:
            fnc = getattr(self._dll, usbxpress_function)
            fnc.restype = ctypes.c_int
            fnc.errcheck = usbxpress_errcheck
    
    def get_num_devices(self):
        """
        This function returns the number of devices connected to the host.

        @return The number of attached USBXpress devices
        """
        num_devices = ctypes.c_ulong()

        self._dll.SI_GetNumDevices(ctypes.byref(num_devices))

        return num_devices.value
    
    def get_product_string(self, device_num, options):
        """
        This function returns a null terminated serial number (S/N) string or
        product description string for the device specified by an index passed in
        DeviceNum. The index for the first device is 0 and the last device is the
        value returned by SI_GetNumDevices - 1.

        @return The product string of the device with device number device_num
        """
        device_string = ctypes.create_string_buffer(MAX_STRING_LENGTH)

        self._dll.SI_GetProductString(ctypes.c_ulong(device_num), \
                                      ctypes.byref(device_string), \
                                      ctypes.c_ulong(options))

        return_string = device_string.raw.split(b'\x00')[0].decode()
        return return_string
    
    def get_serial_number(self, device_num):
        """
        This function returns a null terminated serial number (S/N) string for
        the device specified by an index passed in device_num. The index for
        the first device is 0 and the last device is the value returned by
        SI_GetNumDevices - 1.

        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(device_num, 0x00)
    
    def get_description(self, device_num):
        """
        This function returns a null terminated description string for
        the device specified by an index passed in device_num. The index for
        the first device is 0 and the last device is the value returned by
        SI_GetNumDevices - 1.

        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(device_num, 0x01)
    
    def get_link_nam(self, device_num):
        """
        This function returns a null terminated link name string for
        the device specified by an index passed in device_num. The index for
        the first device is 0 and the last device is the value returned by
        SI_GetNumDevices - 1.

        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(device_num, 0x02)
    
    def get_vid(self, device_num):
        """
        This function returns the Vendor ID (VID) for the device specified by 
        an index passed in device_num. The index for the first device is 0 and
        the last device is the value returned by SI_GetNumDevices - 1.

        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(device_num, 0x03)
    
    def get_pid(self, device_num):
        """
        This function returns the Product ID (PID) for the device specified by 
        an index passed in device_num. The index for the first device is 0 and
        the last device is the value returned by SI_GetNumDevices - 1.

        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(device_num, 0x04)
    
    def get_dll_version(self):
        """
        Obtains the version of the DLL that is currently in use.

        @return The version of the DLL as a string
        """
        high_version = ctypes.c_ulong()
        low_version = ctypes.c_ulong()

        self._dll.SI_GetDLLVersion(ctypes.byref(high_version),
                                   ctypes.byref(low_version))
        
        a = (high_version.value >> 16) & 0xFFFF
        b = high_version.value & 0xFFFF
        c = (low_version.value >> 16) & 0xFFFF
        d = low_version.value & 0xFFFF
        
        return ("%d.%d.%d.%d" % (a, b, c, d))

    def get_driver_version(self):
        """
        Obtains the version of the Driver that is currently in the Windows System
        directory.

        @return The version of the driver as a string
        """
        high_version = ctypes.c_ulong()
        low_version = ctypes.c_ulong()

        self._dll.SI_GetDriverVersion(ctypes.byref(high_version),
                                      ctypes.byref(low_version))
        
        a = (high_version.value >> 16) & 0xFFFF
        b = high_version.value & 0xFFFF
        c = (low_version.value >> 16) & 0xFFFF
        d = low_version.value & 0xFFFF
        
        return ("%d.%d.%d.%d" % (a, b, c, d))

class USBXpressDevice(USBXpressLib):
    """
    This class provides an interface to a USBXpress device. It wraps the 
    USBXpress DLL (SiUSBXp.dll), and it inherits some of its functions from 
    USBXpressLib.
    
    Class methods:
    __init__ -- class constructor
    
    """
    def __init__(self, device_num = 0):
        """
        Class constructor.
        
        Keyword arguments:
        device_num - the device number of the device to use
        """
        self.device_num = device_num
        self._handle = None
        super(USBXpressDevice, self).__init__()
    
    def get_product_string(self, options):
        """
        This function returns a null terminated serial number (S/N) string or
        product description string for the device.

        @return The product string of the device with device number device_num
        """
        return super(USBXpressDevice, self).get_product_string(self.device_num,
                                                               options)
    
    def get_serial_number(self):
        """
        This function returns a null terminated serial number (S/N) string for
        the device.
        
        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(0x00)
    
    def get_description(self):
        """
        This function returns a null terminated description string for
        the device.
        
        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(0x01)
    
    def get_link_name(self):
        """
        This function returns a null terminated link name string for
        the device.
        
        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(0x02)
    
    def get_vid(self):
        """
        This function returns the Vendor ID (VID) for the device.
        
        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(0x03)
    
    def get_pid(self):
        """
        This function returns the Product ID (PID) for the device.
        
        @return The serial number string of the device with device number
                device_num
        """
        return self.get_product_string(0x04)
    
    def open(self):
        """
        Opens a device (using device number sent to the class constructor).
        """
        handle = ctypes.c_void_p()

        self._dll.SI_Open(ctypes.c_ulong(self.device_num), ctypes.byref(handle))
        self._handle = handle

    def close(self):
        """
        Closes an open device using the handle provided by SI_Open.
        """
        self._dll.SI_Close(self._handle)
        self._handle = None

    def _to_bytes(self, seq):
        """
        Internal function to convert a sequence to a bytes type.
        """
        if isinstance(seq, bytes):
            return seq
        elif isinstance(seq, bytearray):
            return bytes(seq)
        elif isinstance(seq, memoryview):
            return seq.tobytes()
        elif isinstance(seq, str) and sys.version_info >= (3,0):
            return seq.encode()
        else:
            b = bytearray()
            for item in seq:
                b.append(item)
            return bytes(b)
    
    def read(self, num_bytes = 4096, o = None):
        """
        Reads the available number of bytes into the supplied buffer and retrieves
        the number of bytes that were read (this can be less than the number of
        bytes requested). This function returns synchronously if the overlapped
        object is set to NULL (this happens by default) but will not block system
        execution. If an initialized OVERLAPPED object is passed then the function
        returns immediately. If the read completed then the status will be
        SI_SUCCESS but if I/O is still pending then it will return STATUS_IO_PENDING.
        If STATUS_IO_PENDING is returned, the OVERLAPPED object can then be waited
        on using WaitForSingleObject(), and retrieve data or  cancel using
        GetOverlappedResult() (as documented on MSDN by Microsoft) or SI_CancelIo(),
        respectively.  This functionality allows for multiple reads to be issued and
        waited on at a time. If any data is available when SI_Read is called it will
        return so check NumBytesReturned to determine if all requested data was
        returned. To make sure that SI_Read returns the requested number of bytes
        use SI_CheckRxQueue() described in Section "3.11. SI_CheckRXQueue" on page 9.

        @return A buffer of type bytes holding the data returned
        """
        buf = ctypes.create_string_buffer(MAX_STRING_LENGTH)
        num_bytes_returned = ctypes.c_ulong()

        self._dll.SI_Read(self._handle,
                          ctypes.byref(buf),
                          ctypes.c_ulong(num_bytes),
                          ctypes.byref(num_bytes_returned),
                          o)

        if num_bytes_returned.value > 0:
            read_buf = buf.raw[:num_bytes_returned.value]
        else:
            read_buf = bytes()
        
        return bytes(read_buf)

    def write(self, data, o = None):
        """
        Writes the specified number of bytes from the supplied buffer to the
        device. This function returns synchronously if the overlapped object is set
        to NULL (this happens by default) but will not block system execution. An
        initialized OVERLAPPED object may be specified and waited on just as 
        described in the description for SI_Read(), Section "3.5. SI_Read" on
        page 6.

        @return The number of bytes that were sent to the device
        """
        data = self._to_bytes(data)
        buf = ctypes.c_char_p(data)
        num_bytes_to_write = ctypes.c_ulong(len(data))
        num_bytes_written = ctypes.c_ulong()

        self._dll.SI_Write(self._handle,
                           buf,
                           num_bytes_to_write,
                           ctypes.byref(num_bytes_written),
                           o)
                
        return num_bytes_written.value

    def cancel_io(self):
        """
        Cancels any pending IO on a device opened with an OVERLAPPED object.
        """
        self._dll.SI_CancelIo(self._handle)

    def flush_buffers(self, flush_transmit = False, flush_receive = False):
        """
        On USB MCU devices, this function flushes both the receive buffer in
        the USBXpress device driver and the transmit buffer in the device. Note:
        Parameter 2 and 3 have no effect and any value can be passed when used
        with USB MCU devices. On CP210x devices, this function operates in
        accordance with parameters 2 and 3. If parameter 2 (flush_transmit) is
        non-zero, the CP210x device's UART transmit buffer is flushed. If
        parameter 3 (flush_receive) is non-zero, the CP210x device's UART
        receive buffer is flushed. If parameters 2 and 3 are both non-zero,
        then both the CP210x device UART transmit buffer and UART receive
        buffer are flushed.
        """
        self._dll.SI_FlushBuffers(self._handle,
                                  ctypes.c_byte(flush_transmit),
                                  ctypes.c_byte(flush_receive))

    def set_timeouts(self, read_timeout = 0, write_timeout = 0):
        """
        Sets the read and write timeouts. Timeouts are used for SI_Read and 
        SI_Write when called synchronously (OVERLAPPED* o is set to NULL). The 
        default value for timeouts is INFINITE (0xFFFFFFFF), but they can be set 
        to wait for any number of milliseconds between 0x0 and 0xFFFFFFFE. 
        """
        self._dll.SI_SetTimeouts(ctypes.c_ulong(read_timeout),
                                 ctypes.c_ulong(write_timeout))

    def get_timeouts(self):
        """
        Returns the current read and write timeouts. If a timeout value is 
        0xFFFFFFFF (INFINITE) it has been set to wait infinitely; otherwise the
        timeouts are specified in milliseconds.

        @return (read_timeout, write_timeout)
        """
        read_timeout = ctypes.c_ulong()
        write_timeout = ctypes.c_ulong()

        self._dll.SI_GetTimeouts(ctypes.byref(read_timeout),
                                 ctypes.byref(write_timeout))
                
        return (read_timeout.value, write_timeout.value)

    def check_rx_queue(self):
        """
        Returns the number of bytes in the receive queue and a status value that 
        indicates if an overrun (SI_QUEUE_OVERRUN) has occurred and if the RX queue
        is ready (SI_QUEUE_READY) for reading. Upon indication of an Overrun 
        condition it is recommended that data transfer be stopped and all buffers be
        flushed using the SI_FlushBuffers command.

        @return (num_bytes_in_rx_queue, queue_status)
        """
        num_bytes_in_rx_queue = ctypes.c_ulong()
        queue_status = ctypes.c_ulong()

        self._dll.SI_CheckRXQueue(self._handle,
                                  ctypes.byref(num_bytes_in_rx_queue),
                                  ctypes.byref(queue_status))
                
        return (num_bytes_in_rx_queue.value, RX_FLAGS[queue_status.value])

    def set_baud_rate(self, baud_rate):
        """
        Sets the Baud Rate. Refer to the device data sheet for a list of Baud 
        Rates supported by the device.
        """
        self._dll.SI_SetBaudRate(self._handle,
                                 ctypes.c_ulong(baud_rate))

    def set_line_control(self, word_length, parity, stop_bits):
        """
        Adjusts the line control settings: word length, stop bits, and parity.
        Refer to the device data sheet for valid line control settings.
        """
        WORD_LENGTH_OPTIONS = {5: 0x0500,
                               6: 0x0600,
                               7: 0x0700,
                               8: 0x0800}
        
        PARITY_OPTIONS = {'N': 0x0000,
                          'O': 0x0010,
                          'E': 0x0020,
                          'M': 0x0030,
                          'S': 0x0040}
        
        STOP_BITS_OPTIONS = {'1': 0x0000,
                             '1.5': 0x0001,
                             '2': 0x0002}

        line_control = STOP_BITS_OPTIONS[stop_bits] | \
                       PARITY_OPTIONS[parity] | \
                       WORD_LENGTH_OPTIONS[word_length]

        self._dll.SI_SetLineControl(self._handle,
                                    ctypes.c_ushort(line_control))

    def set_flow_control(self, 
                         cts_mask_code,
                         rts_mask_code,
                         dtr_mask_code,
                         dsr_mask_code,
                         dcd_mask_code,
                         flow_xon_xoff):
        """
        Adjusts the flow control settings for CTS, RTS, DTR, DSR, DCD, and 
        software (XON/XOFF) flow control.
        Refer to the device data sheet for valid flow control settings.
        """
        MASK_CODES = { 'SI_HELD_INACTIVE'          : 0x00,
                       'SI_HELD_ACTIVE'            : 0x01,
                       'SI_FIRMWARE_CONTROLLED'    : 0x02,
                       'SI_RECEIVE_FLOW_CONTROL'   : 0x02,
                       'SI_TRANSMIT_ACTIVE_SIGNAL' : 0x03,
                       'SI_STATUS_INPUT'           : 0x00,
                       'SI_HANDSHAKE_LINE'         : 0x01,
                      }

        self._dll.SI_SetFlowControl(self._handle,
                                    ctypes.c_byte(MASK_CODES[cts_mask_code]),
                                    ctypes.c_byte(MASK_CODES[rts_mask_code]),
                                    ctypes.c_byte(MASK_CODES[dtr_mask_code]),
                                    ctypes.c_byte(MASK_CODES[dsr_mask_code]),
                                    ctypes.c_byte(MASK_CODES[dcd_mask_code]),
                                    ctypes.c_byte(flow_xon_xoff))

    def get_modem_status(self):
        """
        Gets the Modem Status from the device. This includes the modem pin states.

        @return The status of the modem pins
        """
        modem_status = ctypes.c_byte()

        self._dll.SI_GetModemStatus(self._handle,
                                    ctypes.byref(modem_status))
                
        return modem_status.value

    def set_break(self, break_state = True):
        """
        Sends a break state (transmit or reset) to a CP210x device. Note that
        this function is not necessarily synchronized with queued transmit data.
        """
        self._dll.SI_SetBreak(self._handle,
                              ctypes.c_ushort(break_state))

    def read_latch(self):
        """
        Gets the current port latch value (least significant four bits) from the
        device.

        @return Latch values
        """
        latch = ctypes.c_byte()

        self._dll.SI_ReadLatch(self._handle, ctypes.byref(latch))
                
        return latch.value

    def write_latch(self, mask, latch):
        """
        Sets the current port latch value (least significant four bits) from the
        device.
        """
        self._dll.SI_WriteLatch(self._handle,
                                ctypes.c_byte(mask),
                                ctypes.c_byte(latch))

    def get_part_number(self):
        """
        Retrieves the part number of the CP210x device for a given handle.

        @return PartNum
        """
        PART_NUMBERS = { 0x01 : "SI_CP2101_VERSION",
                         0x02 : "SI_CP2102_VERSION",
                         0x03 : "SI_CP2103_VERSION",
                         0x04 : "SI_CP2104_VERSION",
                         0x05 : "SI_CP2105_VERSION",
                         0x08 : "SI_CP2108_VERSION",
                         0x09 : "SI_CP2109_VERSION",
                         0x80 : "SI_USBXPRESS_EFM8",
                         0x81 : "SI_USBXPRESS_EFM32",
                        }
        part_num = ctypes.c_uint8()

        self._dll.SI_GetPartNumber(self._handle,
                                   ctypes.byref(part_num))
        return PART_NUMBERS[part_num.value]
        
    def get_part_library_version(self):
        """
        Retrieves the library version of the connected USBXPRESS device.

        @return PartNum
        """
        library_version = (ctypes.c_byte * 2)()
        
        self._dll.SI_GetPartLibraryVersion(self._handle,
                                           ctypes.byref(library_version))
        
        return (self._convert_library_version_to_integer(
                "%d.%d" % (library_version[0], library_version[1])))

    def device_io_control(self,
                          io_control_code,
                          string = '',
                          num_bytes_to_read = 0):
        """
        Interface for any miscellaneous device control functions. A separate call
        to SI_DeviceIOControl is required for each input or output operation. A 
        single call cannot be used to perform both an input and output operation 
        simultaneously. Refer to DeviceIOControl function definition on MSDN Help
        for more details.
        
        @return A tuple in the form (return_string, bytes_succeeded), where:
                    - return_string is the data returned
                    - bytes_succeeded is the number of bytes successfully
                      written to the device
        """
        in_buf = ctypes.create_string_buffer(MAX_STRING_LENGTH)
        bytes_succeeded = ctypes.c_ulong()
        out_buf = ctypes.c_char_p(string.encode('utf-8'))
        bytes_to_write = ctypes.c_ulong(len(string))

        self._dll.SI_DeviceIOControl(self._handle,
                                     ctypes.c_ulong(io_control_code),
                                     ctypes.byref(in_buf),
                                     ctypes.c_ulong(num_bytes_to_read),
                                     out_buf,
                                     bytes_to_write,
                                     ctypes.byref(bytes_succeeded))
        
        return (in_buf.raw.split(b'\x00')[0].decode(), bytes_succeeded.value)
    
    def _convert_bcd_to_integer(self, value):
        """
        Convert an BCD-encoded byte value to an integer value.
        
        Keyword arguments:
        value -- the value to convert to integer format
        
        Returns an normal integer.
        """
        return (value & 0x0F) + (((value & 0xF0) >> 4) * 10)
    
    def _convert_library_version_to_integer(self, library_version):
        """
        Converts a BCD-encoded library version string of the form "MAJ.MIN" to a
        normal integer value.
        
        Keyword arguments:
        library_version -- the BCD-encoded library version string in the
                           form "MAJ.MIN"
        
        Returns the string in regular integer encoding
        """
        maj, min = library_version.split(".")
        return "%s.%s" % (self._convert_bcd_to_integer(int(maj)),
                          self._convert_bcd_to_integer(int(min)))

def test_api():
    """
    Calls all functions in the SiUSBXp.dll API
    """
    import logging
    
    logging.basicConfig(level=logging.DEBUG,
                        format='%(message)s')
    logging.info("\n\n")

    my_lib = USBXpressLib()
    logging.info("SI_GetNumDevices()")
    logging.info("--------------------------------------------------------------------------------")
    try:
        num_devices = my_lib.get_num_devices()
    except USBXpressException as e:
        logging.info("Status:                 %s\n\n" % e.value)
    else:
        logging.info("Status:                 %s" % "SI_SUCCESS")
        logging.info("NumDevices:             %s\n\n" % num_devices)

    # For each device, test the following:
    for device_num in range(num_devices):
        my_device = USBXpressDevice(device_num)
        
        # SI_GetProductString
        logging.info("SI_GetProductString (DeviceNum = %d)" % device_num)
        logging.info("--------------------------------------------------------------------------------")
        for option in PRODUCT_STRING_OPTIONS:
            logging.info("String:                 %s" % PRODUCT_STRING_OPTIONS[option])
            try:
                product_string = my_device.get_product_string(option)
            except USBXpressException:
                logging.info("Status:                 %s\n\n" % e.value)
            else:
                logging.info("Status:                 %s" % "SI_SUCCESS")
                logging.info("ProductString:          %s\n\n" % product_string)
            finally:
                pass
        
        # SI_Open
        logging.info("SI_Open(DeviceNum = %d)" % device_num)
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.open()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass
        
        # SI_Write
        logging.info("SI_Write(DeviceHandle, string)")
        logging.info("--------------------------------------------------------------------------------")
        buffer_written = "For every epsilon, there exists a delta."
        try:
            num_bytes_written = my_device.write(buffer_written)
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("BufferWritten:          %s" % buffer_written)
            logging.info("NumBytesWritten:        %d\n\n" % num_bytes_written)
        finally:
            pass
        
        # SI_Read
        logging.info("SI_Read(DeviceHandle, NumBytesToRead = %d)" % num_bytes_written)
        logging.info("--------------------------------------------------------------------------------")
        try:
            string = my_device.read(num_bytes_written)
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("String:                 %s" % string)
            logging.info("NumBytesReturned:       %d\n\n" % len(string))
        finally:
            pass
        
        # SI_CancelIo
        logging.info("SI_CancelIo(DeviceHandle)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.cancel_io()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass
        
        # SI_FlushBuffers
        logging.info("SI_FlushBuffers(DeviceHandle, FlushTransmit = True, FlushReceive = True)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.flush_buffers(flush_transmit = True, flush_receive = True)
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass
        
        # SI_SetTimeouts
        read_timeout = 1234
        write_timeout = 54321
        logging.info("SI_SetTimeouts(ReadTimeout = %d, WriteTimeout = %d)" % (read_timeout, write_timeout))
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.set_timeouts(1234, 54321)
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass
        
        # SI_GetTimeouts
        logging.info("SI_GetTimeouts()")
        logging.info("--------------------------------------------------------------------------------")
        try:
            read_timeout, write_timeout = my_device.get_timeouts()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("ReadTimeout:            %d" % read_timeout)
            logging.info("WriteTimeout:           %d\n\n" % write_timeout)
        finally:
            pass
        
        # SI_CheckRXQueue
        logging.info("SI_CheckRXQueue(DeviceHandle)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            num_bytes_in_rx_queue, queue_status = my_device.check_rx_queue()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("NumBytesInQueue:        %d" % num_bytes_in_rx_queue)
            logging.info("QueueStatus:            %s\n\n" % queue_status)
        finally:
            pass
        
        # SI_SetBaudRate
        logging.info("SI_SetBaudRate(DeviceHandle, BaudRate = 115200)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.set_baud_rate(115200)
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass

        # SI_SetLineControl
        logging.info("SI_SetLineControl(DeviceHandle, WordLength, Parity, StopBits)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.set_line_control(8, 'N', '1')
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass
        
        # SI_SetFlowControl
        logging.info("SI_SetFlowControl(DeviceHandle, CTS_MaskCode, RTS_MaskCode, DTR_MaskCode, ")
        logging.info("                  DSRMaskCode, DCD_MaskCode, FlowXonXoff)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.set_flow_control('SI_STATUS_INPUT', \
                                       'SI_HELD_INACTIVE', \
                                       'SI_HELD_INACTIVE', \
                                       'SI_STATUS_INPUT', \
                                       'SI_STATUS_INPUT', \
                                       0x00)
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass

        # SI_GetModemStatus
        logging.info("SI_GetModemStatus(DeviceHandle)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            modem_status = my_device.get_modem_status()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("ModemStatus:            0x%02x\n\n" % modem_status)
        finally:
            pass
        
        # SI_SetBreak
        logging.info("SI_SetBreak(DeviceHandle, BreakState)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.set_break(True)
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass
        
        # SI_ReadLatch
        logging.info("SI_ReadLatch(DeviceHandle)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            latch = my_device.read_latch()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("Latch:                  0x%02x\n\n" % latch)
        finally:
            pass
        
        # SI_WriteLatch
        logging.info("SI_WriteLatch(DeviceHandle, Mask, Latch)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.write_latch(0x0, 0x0)
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass
        
        # SI_GetPartNumber
        logging.info("SI_GetPartNumber(DeviceHandle)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            part_num = my_device.get_part_number()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("PartNum:                %s\n\n" % part_num)
        finally:
            pass
        
        # SI_GetPartLibraryVersion
        logging.info("SI_GetPartLibraryVersion(DeviceHandle)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            part_library_version = my_device.get_part_library_version()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("LibVersion:             %s\n\n" % part_library_version)
        finally:
            pass
        
        # SI_DeviceIOControl
        logging.info("SI_DeviceIOControl(DeviceHandle, Mask, Latch)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            in_buffer, bytes_succeeded = my_device.device_io_control(0x0)
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass
        
        # SI_GetDLLVersion
        logging.info("SI_GetDLLVersion()")
        logging.info("--------------------------------------------------------------------------------")
        try:
            version = my_device.get_dll_version()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("DLL Version:            %s\n\n" % version)
        finally:
            pass
        
        # SI_GetDriverVersion
        logging.info("SI_GetDriverVersion()")
        logging.info("--------------------------------------------------------------------------------")
        try:
            version = my_device.get_driver_version()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s" % "SI_SUCCESS")
            logging.info("Driver Version:         %s\n\n" % version)
        finally:
            pass
        
        # SI_Close
        logging.info("SI_Close(DeviceHandle)")
        logging.info("--------------------------------------------------------------------------------")
        try:
            my_device.close()
        except USBXpressException as e:
            logging.info("Status:                 %s\n\n" % e.value)
        else:
            logging.info("Status:                 %s\n\n" % "SI_SUCCESS")
        finally:
            pass

if __name__ == "__main__":
    test_api()
