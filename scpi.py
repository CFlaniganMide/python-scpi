"""Generic SCPI commands, allow sending and reading of raw data, helpers to parse information"""
import time
import re

from exceptions import RuntimeError, ValueError
from errors import TimeoutError, CommandError


class scpi(object):
    """Sends commands to the transport and parses return values"""
    def __init__(self, transport, *args, **kwargs):
        super(scpi, self).__init__(*args, **kwargs)
        self.transport = transport
        self.transport.set_message_callback(self.message_received)
        self.message_stack = []
        self.error_format_regex = re.compile(r"([+-]\d+),\"(.*?)\"")
        self.command_timeout = 1.5 # Seconds
        self.ask_default_wait = 0 # Seconds
    
    def message_received(self, message):
        #print " *** Got message '%s' ***" % message
        self.message_stack.append(message)
        pass

    def parse_error(self, message):
        """Parses given message for error code and string, raises error if message format is invalid"""
        match = self.error_format_regex.search(message)
        if not match:
            # PONDER: Make our own exceptions ??
            raise ValueError("message '%s' does not have correct error format" % message)
        code = int(match.group(1))
        errstr = match.group(2)
        return (code, errstr)

    def send_command(self, command, expect_response=True, force_wait=0):
        """Sends the command, waits for all data to complete (and if response is expected for new entry to message stack).
        The force_wait parameter is in seconds, if we know the device is going to take a while processing the request we can use this to avoid nasty race conditions"""
        stack_size_start = len(self.message_stack)
        self.transport.send_command(command)
        time.sleep(force_wait)
        timeout_start = time.time()
        while(   self.transport.incoming_data()
              or (    expect_response
                  and len(self.message_stack) < stack_size_start+1)
              ):
            time.sleep(0)
            if ((time.time() - timeout_start) > self.command_timeout):
                raise TimeoutError(command, self.command_timeout)

    def send_command_and_check(self, command, expect_response=True, force_wait=0):
        """Sends the command and makes sure it did not trigger errors, in case of timeout checks if there was another underlying error and raises that instead
        The force_wait parameter is in seconds, if we know the device is going to take a while processing the request we can use this to avoid nasty race conditions"""
        re_raise = None
        try:
            self.send_command(command, expect_response, force_wait)
        except (TimeoutError), e:
            re_raise = e
        finally:
            self.send_command("SYST:ERR?", True)
            code, errstr = self.parse_error(self.message_stack[-1])
            if code != 0:
                raise CommandError(command, code, errstr)
            # Pop the no-error out
            self.message_stack.pop()
            if re_raise:
                raise re_raise

    def parse_number(self, message):
        """This is pretty trivial but just in case we want to change from floats to Decimals for example"""
        return float(message)

    def pop_and_parse_number(self):
        """Pops the last value from message stack and parses number from it"""
        data = self.message_stack.pop()
        return self.parse_number(data)

    def ask_number(self, command, force_wait=None):
        """Sends the command (checking for errors), then pops and parses the last line as number
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        if force_wait == None:
            force_wait = self.ask_default_wait
        self.send_command_and_check(command, True, force_wait)
        return self.pop_and_parse_number()
        # TODO: Before returning check if there are leftover messages in the stack, that would not be a good thing...

    def pop_and_parse_boolean(self):
        """Pops the last value from message stack and parses it as boolean"""
        data = self.message_stack.pop()
        return bool(int(data))


class scpi_device(object):
    """Implements nicer wrapper methods for the raw commands from the generic SCPI command set"""

    def __init__(self, transport, *args, **kwargs):
        """Initializes a device for the given transport"""
        super(scpi_device, self).__init__(*args, **kwargs)
        self.scpi = scpi(transport)
        # always reset to known status on init
        self.reset()

    def reset(self):
        """Resets the device to known state (with *RST) and clears the error log"""
        return self.scpi.send_command("*RST;*CLS", False)

    def measure_voltage(self, extra_params=""):
        """Returns the measured (scalar) actual output voltage (in volts), pass extra_params string to append to the command (like ":ACDC")"""
        return self.scpi.ask_number("MEAS:SCAL:VOLT%s?" % extra_params)

    def measure_current(self, extra_params=""):
        """Returns the measured (scalar) actual output current (in amps), pass extra_params string to append to the command (like ":ACDC")"""
        return self.scpi.ask_number("MEAS:SCAL:CURR%s?" % extra_params)

    def set_measure_current_max(self, amps):
        """Sets the upper bound (in amps) of current to measure, on some devices low-current accuracy can be increased by keeping this low"""
        return self.scpi.send_command_and_check("SENS:CURR:RANG %f" % amps, False)

    def query_measure_current_max(self):
        """Returns the upper bound (in amps) of current to measure, this is not neccessarily same number as set with set_measure_current_max"""
        return self.scpi.ask_number("SENS:CURR:RANG?")

    def set_voltage(self, millivolts, extra_params=""):
        """Sets the desired output voltage (but does not auto-enable outputs) in millivolts, pass extra_params string to append to the command (like ":PROT")"""
        self.scpi.send_command_and_check("SOUR:VOLT%s %f MV" % (extra_params, millivolts), False)

    def query_voltage(self, extra_params=""):
        """Returns the set output voltage (in volts), pass extra_params string to append to the command (like ":PROT")"""
        return self.scpi.ask_number("SOUR:VOLT%s?" % extra_params)

    def set_current(self, milliamps, extra_params=""):
        """Sets the desired output current (but does not auto-enable outputs) in milliamps, pass extra_params string to append to the command (like ":TRIG")"""
        return self.scpi.send_command_and_check("SOUR:CURR%s %f MA" % (extra_params, milliamps), False)

    def query_current(self, extra_params=""):
        """Returns the set output current (in amps), pass extra_params string to append to the command (like ":TRIG")"""
        return self.scpi.ask_number("SOUR:CURR%s?" % extra_params)

    def set_output(self, state):
        """Enables/disables output"""
        return self.scpi.send_command_and_check("OUTP:STAT %d" % state, False)

    def query_output(self):
        """Returns the output state"""
        self.scpi.send_command("OUTP:STAT?", True)
        return self.scpi.pop_and_parse_boolean()

