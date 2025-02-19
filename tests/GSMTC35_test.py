#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
  Automatic test of GSMTC35 library with fake serial port (using a Mock) and
  getting stdout with a specific class.
"""

import unittest
from GSMTC35 import GSMTC35
import logging
import re
import datetime
import time
import sys

# Python 2.7/3  (Mock)
if sys.version_info >= (3, 3):
  from unittest.mock import patch
else:
  from mock import patch

# Python 2.7/3 compatibility (StringIO)
try:
  from StringIO import StringIO
except ImportError:
  from io import StringIO

class CapturingStdOut(list):
  """
  Capture stdout and give it back into a variable.

  Example:
  with CapturingStdOut() as std_output:
    anyFunctionHere()
  print(std_output)
  """
  def __enter__(self):
    self._stdout = sys.stdout
    sys.stdout = self._stringio = StringIO()
    return self
  def __exit__(self, *args):
    self.extend(self._stringio.getvalue().splitlines())
    del self._stringio    # free up some memory
    sys.stdout = self._stdout

class MockSerial:
  """
  Simulate Serial port to:
    - Verify data sent by the library to the serial port (regex or strict comparison)
    - Send data from the serial port to the library
    - Simulate serial port delay while sending data from the serial port to the library
  """
  __is_open = True
  __read_write = []
  __timestamp_begin_delay = None

  @staticmethod
  def getDefaultConfigForSetup():
    """Get configuration to use to have a working GSMTC35.setup()
    """
    return [
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ]

  @staticmethod
  def initializeMock(read_write, is_open = True):
    """Initialize the Serial port mock

    Keyword arguments:
      read_write -- (list of any number of dict like this:
                      - {'IN': b'data_sent_by_lib_here', 'mode'(optional): 'regex/strict_compare'}
                      - {'OUT': b'data_sent_by_fake_gsm_module_here', 'wait_ms'(optional): Any_delay_here_as_uint}
                    ) Data to simulate gsm module and verify data sent to gsm module by library
      is_open -- (bool, default: True) Is module open ?
    """
    MockSerial.__is_open = is_open
    MockSerial.__read_write = read_write
    MockSerial.__timestamp_begin_delay = None

  def __init__(self, port="", baudrate="", parity="", stopbits="", bytesize="", timeout=""):
    return

  def inWaiting(self):
    """Fake serial.inWaiting function
    Will return 0 if no data to send (first element in read_write list not an 'OUT' or if the 'wait_ms' is not yet finished)
    Else, will return length of the 'OUT' data to send.

    Note: If this function (or read()) is requested, the 'wait_ms' timer begins
    """
    if MockSerial.__is_open and len(MockSerial.__read_write) > 0:
      if 'OUT' in MockSerial.__read_write[0]:
        if 'wait_ms' in MockSerial.__read_write[0]:
          if MockSerial.__timestamp_begin_delay == None:
            MockSerial.__timestamp_begin_delay = 1000 * time.time()
            logging.debug("Begining fake serial port delay of "+str(MockSerial.__read_write[0]['wait_ms'])+" seconds")
            return 0
          elif MockSerial.__timestamp_begin_delay + int(MockSerial.__read_write[0]['wait_ms']) > 1000 * time.time():
            return 0
          else:
            return len(MockSerial.__read_write[0]['OUT'])
        else:
          return len(MockSerial.__read_write[0]['OUT'])

    return 0

  def read(self, size_to_read):
    """Fake serial.read function
    Will return None if no data to send (first element in read_write list not an 'OUT')
    Else, will return the requested number of bytes of 'OUT' data (or the integrality if too much requested) after the 'wait_ms' timer is finished
    """
    if MockSerial.__is_open and len(MockSerial.__read_write) > 0:
      if 'OUT' in MockSerial.__read_write[0]:
        if 'wait_ms' in MockSerial.__read_write[0]:
          fake_delay = 0
          if MockSerial.__timestamp_begin_delay == None:
            MockSerial.__timestamp_begin_delay = 1000 * time.time()
            fake_delay = int(MockSerial.__read_write[0]['wait_ms'])/1000
          elif MockSerial.__timestamp_begin_delay + int(MockSerial.__read_write[0]['wait_ms']) > 1000*time.time():
            fake_delay = (int(MockSerial.__read_write[0]['wait_ms'])/1000) - ((1000*time.time() - MockSerial.__timestamp_begin_delay)/1000)

          if fake_delay > 0:
            logging.debug("Fake serial port delay of "+str(fake_delay)+" seconds in progress before sending data")
            time.sleep(fake_delay)

        if size_to_read < len(MockSerial.__read_write[0]['OUT']):
          val = MockSerial.__read_write[0]['OUT'][:size_to_read]
          MockSerial.__read_write[0]['OUT'] = MockSerial.__read_write[0]['OUT'][size_to_read:]
          return val
        else:
          val = MockSerial.__read_write[0]['OUT']
          MockSerial.__read_write.pop(0)
          MockSerial.__timestamp_begin_delay = None
          return val

    return None

  def write(self, data):
    """Fake serial.write function
    Will throw an AssertionError if comparison between first element of read_write is not the same (or regex) as what was sent by the library
    """
    if MockSerial.__is_open and len(MockSerial.__read_write) > 0:
      if 'IN' in MockSerial.__read_write[0]:
        check_val = MockSerial.__read_write[0]['IN']

        test_mode = "strict_compare"
        if 'mode' in MockSerial.__read_write[0]:
          test_mode = MockSerial.__read_write[0]["mode"]

        if test_mode == "strict_compare":
          if str(data) != str(check_val):
            raise AssertionError('Mock Serial: Should write "' + str(check_val) + '" but "'+str(data)+'" requested (strict compare)')
        elif test_mode == "regex":
          if not re.search(check_val, data):
            raise AssertionError('Mock Serial: Should write "' + str(check_val) + '" but "'+str(data)+'" requested (regex compare)')
        else:
          raise AssertionError('Mock Serial: Invalid test_mode (should be "regex" or "strict_compare" (default)')

        MockSerial.__read_write.pop(0)
        return len(data)
    return 0

  def isOpen(self):
    """Fake serial.isOpen function
    Will return is_open registered in initializeMock
    """
    return MockSerial.__is_open

  def close(self):
    """Fake serial.close function
    Will return True all the time
    """
    return True

class TestGSMTC35(unittest.TestCase):
  """
  Test all the GSMTC35 class using fake serial port (MockSerial) and getting the std output (CapturingStdOut)
  """
  def setUp(self):
    """
    Get test begining timestamp (used to show time to execute test at the end)
    """
    self.startTime = time.time()
    
    # Show full difference between 2 values that we wanted to be equal
    self.maxDiff = None

  def tearDown(self):
    """
    Show the execution time of the test
    """
    t = time.time() - self.startTime
    print(str(self.id())+": "+str(round(t, 2))+ " seconds")


  @patch('serial.Serial', new=MockSerial)
  def test_all_cmd_request_except_help_cmd(self):
    logging.debug("test_all_cmd_request_except_help_cmd")

    # Request failed because nothing requested
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--baudrate', '115200', '--serialPort', 'COM_Invalid', '--pin', '1234', '--puk', '12345678', '--pin2', '1234', '--puk2', '12345678', '--nodebug', '--debug']))
    self.assertNotEqual(cm.exception.code, 0)
    self.assertTrue("Debugging..." in std_output)
    self.assertTrue("Baudrate: 115200" in std_output)
    self.assertTrue("Serial port: COM_Invalid" in std_output)
    self.assertTrue("PIN: 1234" in std_output)
    self.assertTrue("PUK: 12345678" in std_output)
    self.assertTrue("PIN2: 1234" in std_output)
    self.assertTrue("PUK2: 12345678" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE']))
    self.assertEqual(cm.exception.code, 1)
    self.assertTrue("[ERROR] You must call one action, use '-h' to get more information." in std_output)

    # Request failed because invalid argument
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--undefinedargument']))
    self.assertNotEqual(cm.exception.code, 0)
    self.assertTrue("[ERROR] option --undefinedargument not recognized" in std_output)

    # Impossible to get pin status
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: UNDEFINED\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--isAlive']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("[ERROR] Failed to check PIN status" in std_output)

    # PIN still needed (should never happen but safeguard)
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PIN\r\n'}, {'OUT': b'OK\r\n'}    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--isAlive']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("[ERROR] SIM PIN is needed" in std_output)

    # --isAlive
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT\r\n'}, {'OUT': b'OK\r\n'},
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--isAlive']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("Is alive: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT\r\n'}, {'OUT': b'ERROR\r\n'},
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--isAlive']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("Is alive: False" in std_output)

    # --call
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATD+33601020304;\r\n'}, {'OUT': b'OK\r\n'},
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--call', '+33601020304', 'false']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("Calling +33601020304 in normal mode..." in std_output)
    self.assertTrue("Call picked up: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATD#31#+33601020304;\r\n'}, {'OUT': b'ERROR\r\n'},
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--call', '+33601020304', 'true', '10']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("Calling +33601020304 in invisible mode..." in std_output)
    self.assertTrue("Call picked up: False" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--call', '', 'true', '10']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("[ERROR] You must specify a valid phone number" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--call']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("[ERROR] You must specify a phone number to call" in std_output)

    # --hangUpCall
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--hangUpCall']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("Hanging up call..." in std_output)
    self.assertTrue("Hang up call: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CHUP\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'ATH\r\n'}, {'OUT': b'ERROR\r\n'},
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--hangUpCall']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("Hanging up call..." in std_output)
    self.assertTrue("Hang up call: False" in std_output)

    # --sendSMS
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGS=24\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203[0-9A-F]{2}00000CD4F29C0E6A97E7F3F0B90C', 'mode': 'regex'},
      {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--sendSMS', '+33601020304', 'Test message']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("SMS sent: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGS=24\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203[0-9A-F]{2}00000CD4F29C0E6A97E7F3F0B90C', 'mode': 'regex'},
      {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--sendSMS', '+33601020304', 'Test message']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("SMS sent: False" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--sendSMS', '+33601020304']))
    self.assertEqual(cm.exception.code, 1)
    self.assertTrue("[ERROR] You need to specify the phone number and the message" in std_output)

    # --sendEncodedSMS
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGS=24\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203[0-9A-F]{2}00000CD4F29C0E6A97E7F3F0B90C', 'mode': 'regex'},
      {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--sendEncodedSMS', '+33601020304', '54657374206D657373616765']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("SMS encoded sent: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGS=24\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203[0-9A-F]{2}00000CD4F29C0E6A97E7F3F0B90C', 'mode': 'regex'},
      {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--sendEncodedSMS', '+33601020304', '54657374206D657373616765']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("SMS encoded sent: False" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--sendEncodedSMS', '+33601020304']))
    self.assertEqual(cm.exception.code, 1)
    self.assertTrue("[ERROR] You need to specify the phone number and the message" in std_output)

    # --sendTextModeSMS
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'Test message\x1a'}, {'OUT': b'OK\r\n'},
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--sendTextModeSMS', '+33601020304', 'Test message']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("SMS sent using Text Mode: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'Test message\x1a'}, {'OUT': b'ERROR\r\n'},
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--sendTextModeSMS', '+33601020304', 'Test message']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("SMS sent using Text Mode: False" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--sendTextModeSMS', '+33601020304']))
    self.assertEqual(cm.exception.code, 1)
    self.assertTrue("[ERROR] You need to specify the phone number and the message" in std_output)

    # --deleteSMS
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGL=4\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--deleteSMS', 'ALL']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("SMS deleted: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGD=4\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--deleteSMS', '4']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("SMS deleted: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGL=4\r\n'},
      {'OUT': b'+CMGL: 9,0,,39\r\n'},
      {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
      {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGD=9\r\n'}, {'OUT': b'ERROR\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--deleteSMS', 'ALL']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("SMS deleted: False" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--deleteSMS']))
    self.assertEqual(cm.exception.code, 1)
    self.assertTrue("[ERROR] You need to specify the type of SMS to delete" in std_output)

    # --getSMS
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGL=4\r\n'},
      {'OUT': b'+CMGL: 9,0,,39\r\n'},
      {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
      {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--getSMS', 'ALL']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("List of SMS:" in std_output)
    self.assertTrue("+31628870634 (id 9, REC UNREAD, 11/01/18 10:37:32 GMT+1.0): This is text message 2" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--getSMS']))
    self.assertEqual(cm.exception.code, 1)
    self.assertTrue("[ERROR] You need to specify the type of SMS to get" in std_output)

    # --getEncodedSMS
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGL=4\r\n'},
      {'OUT': b'+CMGL: 9,0,,39\r\n'},
      {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
      {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--getEncodedSMS', 'ALL']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("List of encoded SMS:" in std_output)
    self.assertTrue("+31628870634 (id 9, REC UNREAD, 7bit, 11/01/18 10:37:32 GMT+1.0): 546869732069732074657874206D6573736167652032" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--getEncodedSMS']))
    self.assertEqual(cm.exception.code, 1)
    self.assertTrue("[ERROR] You need to specify the type of SMS to get" in std_output)

    # --getTextModeSMS
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGL="ALL"\r\n'},
      {'OUT': b'+CMGL: 1,"REC UNREAD","+31628870634",,"11/01/09,10:26:26+04"\r\n'},
      {'OUT': b'This is text message 1\r\n'},
      {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--getTextModeSMS', 'ALL']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("List of text mode SMS:" in std_output)
    self.assertTrue("+31628870634 (id 1, REC UNREAD, 11/01/09 10:26:26+04): This is text message 1" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--getTextModeSMS']))
    self.assertEqual(cm.exception.code, 1)
    self.assertTrue("[ERROR] You need to specify the type of SMS to get" in std_output)

    # --pickUpCall
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATA;\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--pickUpCall']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("Picking up call..." in std_output)
    self.assertTrue("Pick up call: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATA;\r\n'}, {'OUT': b'ERROR\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--pickUpCall']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("Picking up call..." in std_output)
    self.assertTrue("Pick up call: False" in std_output)

    # --isSomeoneCalling
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPAS\r\n'}, {'OUT': b'+CPAS: 3\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--isSomeoneCalling']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("Is someone calling: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPAS\r\n'}, {'OUT': b'+CPAS: 3\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--isSomeoneCalling']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("Is someone calling: True" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPAS\r\n'}, {'OUT': b'+CPAS: 4\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--isSomeoneCalling']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("Is someone calling: False" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPAS\r\n'}, {'OUT': b'ERROR\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--isSomeoneCalling']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("Is someone calling: False" in std_output)

    # --information
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CGMI\r\n'}, {'OUT': b'FAKE_MANUFACTURER\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CGMM\r\n'}, {'OUT': b'FAKE_MODEL\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CGMR\r\n'}, {'OUT': b'FAKE_REVISION\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CGSN\r\n'}, {'OUT': b'FAKE_IMEI\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CIMI\r\n'}, {'OUT': b'FAKE_IMSI\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+COPS=3,0\r\n'}, {'OUT': b'OK\r\n'}, {'IN': b'AT+COPS?\r\n'}, {'OUT': b'+COPS: 0,1,\"FAKE_OPERATOR\"\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CSQ\r\n'}, {'OUT': b'+CSQ: 60,USELESS\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CCLK?\r\n'}, {'OUT': b'+CCLK: 11/12/13,14:15:16\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SLCD\r\n'}, {'OUT': b'^SLCD: 12:34:56\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+COPN\r\n'}, {'OUT': b'+COPN: 1,\"FAKE1\"\r\n'}, {'OUT': b'+COPN: 2,\"FAKE 2\"\r\n'}, {'OUT': b'+COPN: 3,\"Fake Three\"\r\n'}, {'OUT': b'+COPN: DUMMY_ERROR\r\n'},{'OUT': b'DUMMY_ERROR\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLCC\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^MONP\r\n'}, {'OUT': b'chann rs  dBm   PLMN   BCC C1 C2\r\n'}, {'OUT': b'504   18  -78   26203  1   27 28\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CACM?\r\n'}, {'OUT': b'+CACM: FF05\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CAMM?\r\n'}, {'OUT': b'+CAMM: FFFF\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM?\r\n'}, {'OUT': b'^SCTM: DUMMY,0,OTHER_DUMMY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CFUN?\r\n'}, {'OUT': b'+CFUN: 1\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--information']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("GSM module Manufacturer ID: FAKE_MANUFACTURER" in std_output)
    self.assertTrue("GSM module Model ID: FAKE_MODEL" in std_output)
    self.assertTrue("GSM module Revision ID: FAKE_REVISION" in std_output)
    self.assertTrue("Product serial number ID (IMEI): FAKE_IMEI" in std_output)
    self.assertTrue("International Mobile Subscriber Identity (IMSI): FAKE_IMSI" in std_output)
    self.assertTrue("Current operator: FAKE_OPERATOR" in std_output)
    self.assertTrue("Signal strength: 7dBm" in std_output)
    self.assertTrue("Date from internal clock: 2011-12-13 14:15:16" in std_output)
    self.assertTrue("Last call duration: 45296sec" in std_output)
    self.assertTrue("List of stored operators: FAKE1, FAKE 2, Fake Three" in std_output)
    self.assertTrue("Call status: NOCALL" in std_output)
    # Next test is not possible because dict display is not predictible
    #self.assertTrue("Neighbour cells: [{'chann': 504, 'rs': 18, 'dbm': -78, 'plmn': 26203, 'bcc': 1, 'c1': 27, 'c2': 28}]" in std_output)
    self.assertTrue("Accumulated call meter: 65285 home units" in std_output)
    self.assertTrue("Accumulated call meter max: 65535 home units" in std_output)
    self.assertTrue("Is GSM module temperature critical: False" in std_output)
    self.assertTrue("Is GSM module in sleep mode: False" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT\r\n'}, {'OUT': b'ERROR\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--information']))
    self.assertEqual(cm.exception.code, 2)
    self.assertTrue("GSM module is not alive, can't get information" in std_output)

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CGMI\r\n'}, {'OUT': b'FAKE_MANUFACTURER\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CGMM\r\n'}, {'OUT': b'FAKE_MODEL\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CGMR\r\n'}, {'OUT': b'FAKE_REVISION\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CGSN\r\n'}, {'OUT': b'FAKE_IMEI\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CIMI\r\n'}, {'OUT': b'FAKE_IMSI\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+COPS=3,0\r\n'}, {'OUT': b'OK\r\n'}, {'IN': b'AT+COPS?\r\n'}, {'OUT': b'+COPS: 0,1,\"FAKE_OPERATOR\"\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CSQ\r\n'}, {'OUT': b'+CSQ: INVALID,USELESS\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CCLK?\r\n'}, {'OUT': b'+CCLK: 11/12/13,14:15:16\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SLCD\r\n'}, {'OUT': b'^SLCD: 12:34:56\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+COPN\r\n'}, {'OUT': b'+COPN: 1,\"FAKE1\"\r\n'}, {'OUT': b'+COPN: 2,\"FAKE 2\"\r\n'}, {'OUT': b'+COPN: 3,\"Fake Three\"\r\n'}, {'OUT': b'+COPN: DUMMY_ERROR\r\n'},{'OUT': b'DUMMY_ERROR\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLCC\r\n'}, {'OUT': b'+CLCC: 1,1,5,0,0,"+33601020304",145\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^MONP\r\n'}, {'OUT': b'chann rs  dBm   PLMN   BCC C1 C2\r\n'}, {'OUT': b'504   18  -78   26203  1   27 28\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CACM?\r\n'}, {'OUT': b'+CACM: FF05\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CAMM?\r\n'}, {'OUT': b'+CAMM: FFFF\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM?\r\n'}, {'OUT': b'^SCTM: DUMMY,0,OTHER_DUMMY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CFUN?\r\n'}, {'OUT': b'+CFUN: 1\r\n'}, {'OUT': b'OK\r\n'}
    ])
    with self.assertRaises(SystemExit) as cm:
      with CapturingStdOut() as std_output:
        GSMTC35.main((['--serialPort', 'COM_FAKE', '--information']))
    self.assertEqual(cm.exception.code, 0)
    self.assertTrue("GSM module Manufacturer ID: FAKE_MANUFACTURER" in std_output)
    self.assertTrue("GSM module Model ID: FAKE_MODEL" in std_output)
    self.assertTrue("GSM module Revision ID: FAKE_REVISION" in std_output)
    self.assertTrue("Product serial number ID (IMEI): FAKE_IMEI" in std_output)
    self.assertTrue("International Mobile Subscriber Identity (IMSI): FAKE_IMSI" in std_output)
    self.assertTrue("Current operator: FAKE_OPERATOR" in std_output)
    self.assertTrue("Signal strength: Wrong value" in std_output)
    self.assertTrue("Date from internal clock: 2011-12-13 14:15:16" in std_output)
    self.assertTrue("Last call duration: 45296sec" in std_output)
    self.assertTrue("List of stored operators: FAKE1, FAKE 2, Fake Three" in std_output)
    self.assertTrue("Call status: WAITING (phone number: +33601020304)" in std_output)
    # Next test is not possible because dict display is not predictible
    #self.assertTrue("Neighbour cells: [{'chann': 504, 'rs': 18, 'dbm': -78, 'plmn': 26203, 'bcc': 1, 'c1': 27, 'c2': 28}]" in std_output)
    self.assertTrue("Accumulated call meter: 65285 home units" in std_output)
    self.assertTrue("Accumulated call meter max: 65535 home units" in std_output)
    self.assertTrue("Is GSM module temperature critical: False" in std_output)
    self.assertTrue("Is GSM module in sleep mode: False" in std_output)

  @patch('serial.Serial', new=MockSerial)
  def test_all_cmd_help(self):
    logging.debug("test_all_cmd_help")
    # No paramaters
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main()
    self.assertNotEqual(cm.exception.code, 0)

    # Request basic help
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help"]))
    self.assertEqual(cm.exception.code, 0)

    # Request extended help
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "help"]))
    self.assertEqual(cm.exception.code, 0)

    # Request extended help
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "baudrate"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "serialport"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "pin"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "puk"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "pin2"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "puk2"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "isalive"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "call"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "hangupcall"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "issomeonecalling"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "pickupcall"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "sendsms"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "sendencodedsms"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "sendtextmodesms"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "getsms"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "getencodedsms"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "gettextmodesms"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "deletesms"]))
    self.assertEqual(cm.exception.code, 0)
    with self.assertRaises(SystemExit) as cm:
      GSMTC35.main((["--help", "information"]))
    self.assertEqual(cm.exception.code, 0)

  @patch('serial.Serial', new=MockSerial)
  def test_fail_setup(self):
    logging.debug("test_fail_setup")
    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.setup(_port="COM_FAKE", _pin="1234", _puk="12345678"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.setup(_port="COM_FAKE", _pin="1234", _puk="12345678"))

  @patch('serial.Serial', new=MockSerial)
  def test_success_setup(self):
    logging.debug("test_success_setup")
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    gsm = GSMTC35.GSMTC35()
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'ERROR\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

  def test_fail_use_serial_port(self):
    logging.debug("test_fail_use_serial_port")
    # Do not use Mock on this test in order to trigger an error (Invalid serial port)
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.setup(_port="COM_FAKE"))

  @patch('serial.Serial', new=MockSerial)
  def test_fail_send_get_data_through_serial_port(self):
    logging.debug("test_fail_send_get_data_through_serial_port")
    MockSerial.initializeMock([])
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.isAlive())

    MockSerial.initializeMock([])
    gsm = GSMTC35.GSMTC35()
    self.assertEqual(gsm.getManufacturerId(), "")

    MockSerial.initializeMock([{'IN': b'AT+COPN\r\n'}])
    gsm = GSMTC35.GSMTC35()
    self.assertEqual(gsm.getOperatorNames(), [])

  @patch('serial.Serial', new=MockSerial)
  def test_success_pin_during_setup(self):
    logging.debug("test_success_pin_during_setup")
    # Entered PIN/PUK/PIN2/PUK2
    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PUK2\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN=87654321\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PIN2\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN=4321\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PUK\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN=12345678\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PIN\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN=1234\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: READY\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertTrue(gsm.setup(_port="COM_FAKE", _pin="1234", _puk="12345678", _pin2="4321", _puk2="87654321"))

    # No PIN/PUK/PIN2/PUK2 specified in entry (bypassing)
    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PUK2\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PIN2\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PUK\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PIN\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

  @patch('serial.Serial', new=MockSerial)
  def test_fail_pin_during_setup(self):
    logging.debug("test_fail_pin_during_setup")
    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PUK2\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN=87654321\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.setup(_port="COM_FAKE", _pin="1234", _puk="12345678", _pin2="4321", _puk2="87654321"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PIN2\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN=4321\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.setup(_port="COM_FAKE", _pin="1234", _puk="12345678", _pin2="4321", _puk2="87654321"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PUK\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN=12345678\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.setup(_port="COM_FAKE", _pin="1234", _puk="12345678", _pin2="4321", _puk2="87654321"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: SIM PIN\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN=1234\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.setup(_port="COM_FAKE", _pin="1234", _puk="12345678", _pin2="4321", _puk2="87654321"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CPIN?\r\n'}, {'OUT': b'+CPIN: UNDEFINED\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    gsm = GSMTC35.GSMTC35()
    self.assertFalse(gsm.setup(_port="COM_FAKE", _pin="1234", _puk="12345678", _pin2="4321", _puk2="87654321"))

  @patch('serial.Serial', new=MockSerial)
  def test_all_change_baudrate(self):
    logging.debug("test_all_change_baudrate")
    gsm = GSMTC35.GSMTC35()

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [{'IN': b'AT+IPR=9600\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.changeBaudrateMode(115200, 9600, "COM_FAKE"))

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup() + [{'IN': b'AT+IPR=9600\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.changeBaudrateMode(115200, 9600, "COM_FAKE"))

    MockSerial.initializeMock([
      {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATE0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'ATV1\r\n'}, {'OUT': b'ERROR\r\n'},
      {'IN': b'AT+CMEE=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
      {'IN': b'AT+IPR=115200\r\n'}, {'OUT': b'OK\r\n'}
    ])
    self.assertFalse(gsm.changeBaudrateMode(115200, 9600, "COM_FAKE"))

  @patch('serial.Serial', new=MockSerial)
  def test_all_is_initialized(self):
    logging.debug("test_fail_pin_during_setup")
    gsm = GSMTC35.GSMTC35()

    MockSerial.initializeMock([])
    self.assertFalse(gsm.isInitialized())

    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([])
    self.assertTrue(gsm.isInitialized())

  @patch('serial.Serial', new=MockSerial)
  def test_all_close(self):
    logging.debug("test_all_close")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock([{'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.close(), None)
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))
    MockSerial.initializeMock([{'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.close(), None)

  @patch('serial.Serial', new=MockSerial)
  def test_all_reboot(self):
    logging.debug("test_all_reboot")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CFUN=1,1\r\n'}, {'OUT': b'OK\r\n'},
                               {'OUT': b'... Rebooting ...\r\n'}, {'OUT': b'^SYSSTART\r\n'},
                               {'IN': b'AT+IPR=0\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.reboot())

    MockSerial.initializeMock([{'IN': b'AT+CFUN=1,1\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.reboot())

  @patch('serial.Serial', new=MockSerial)
  def test_all_is_alive(self):
    logging.debug("test_all_is_alive")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.isAlive())

    MockSerial.initializeMock([{'IN': b'AT\r\n'}])
    self.assertFalse(gsm.isAlive())

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_manufacturer_id(self):
    logging.debug("test_all_get_manufacturer_id")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CGMI\r\n'}, {'OUT': b'FAKE_MANUFACTURER\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(str(gsm.getManufacturerId()), "FAKE_MANUFACTURER")

    MockSerial.initializeMock([{'IN': b'AT+CGMI\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(str(gsm.getManufacturerId()), "")

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_model_id(self):
    logging.debug("test_all_get_model_id")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CGMM\r\n'}, {'OUT': b'FAKE_MODEL\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(str(gsm.getModelId()), "FAKE_MODEL")

    MockSerial.initializeMock([{'IN': b'AT+CGMM\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(str(gsm.getModelId()), "")

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_revision_id(self):
    logging.debug("test_all_get_revision_id")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CGMR\r\n'}, {'OUT': b'FAKE_REVISION\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(str(gsm.getRevisionId()), "FAKE_REVISION")

    MockSerial.initializeMock([{'IN': b'AT+CGMR\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(str(gsm.getRevisionId()), "")

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_imei(self):
    logging.debug("test_all_get_imei")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CGSN\r\n'}, {'OUT': b'FAKE_IMEI\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(str(gsm.getIMEI()), "FAKE_IMEI")

    MockSerial.initializeMock([{'IN': b'AT+CGSN\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(str(gsm.getIMEI()), "")

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_imsi(self):
    logging.debug("test_all_get_imsi")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CIMI\r\n'}, {'OUT': b'FAKE_IMSI\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(str(gsm.getIMSI()), "FAKE_IMSI")

    MockSerial.initializeMock([{'IN': b'AT+CIMI\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(str(gsm.getIMSI()), "")

  @patch('serial.Serial', new=MockSerial)
  def test_all_set_module_to_manufacturer_state(self):
    logging.debug("test_all_set_module_to_manufacturer_state")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT&F0\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setModuleToManufacturerState())

    MockSerial.initializeMock([{'IN': b'AT&F0\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.setModuleToManufacturerState())

  @patch('serial.Serial', new=MockSerial)
  def test_all_switch_off(self):
    logging.debug("test_all_switch_off")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT^SMSO\r\n'}, {'OUT': b'MS OFF\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.switchOff())

    MockSerial.initializeMock([{'IN': b'AT^SMSO\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.switchOff())

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_operator_name(self):
    logging.debug("test_all_get_operator_name")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+COPS=3,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+COPS?\r\n'}, {'OUT': b'+COPS: 0,1,\"FAKE_OPERATOR\"\r\n'},
                               {'OUT': b'OK\r\n'}])
    self.assertEqual(str(gsm.getOperatorName()), "FAKE_OPERATOR")

    MockSerial.initializeMock([{'IN': b'AT+COPS=3,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+COPS?\r\n'}, {'OUT': b'+COPS: \"FAKE_OPERATOR\"\r\n'}])
    self.assertEqual(str(gsm.getOperatorName()), "")

    MockSerial.initializeMock([{'IN': b'AT+COPS=3,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+COPS?\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(str(gsm.getOperatorName()), "")

    MockSerial.initializeMock([{'IN': b'AT+COPS=3,0\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(str(gsm.getOperatorName()), "")

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_signal_strength(self):
    logging.debug("test_all_get_signal_strength")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CSQ\r\n'}, {'OUT': b'+CSQ: 60,USELESS\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSignalStrength(), 7)

    MockSerial.initializeMock([{'IN': b'AT+CSQ\r\n'}, {'OUT': b'+CSQ: 100,USELESS\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSignalStrength(), -1)

    MockSerial.initializeMock([{'IN': b'AT+CSQ\r\n'}, {'OUT': b'+CSQ: -1,USELESS\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSignalStrength(), -1)

    MockSerial.initializeMock([{'IN': b'AT+CSQ\r\n'}, {'OUT': b'+CSQ: \r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSignalStrength(), -1)

    MockSerial.initializeMock([{'IN': b'AT+CSQ\r\n'}, {'OUT': b'+CSQ: WRONG,USELESS\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSignalStrength(), -1)

    MockSerial.initializeMock([{'IN': b'AT+CSQ\r\n'}, {'OUT': b'+CSQ: WRONG\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSignalStrength(), -1)

    MockSerial.initializeMock([{'IN': b'AT+CSQ\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getSignalStrength(), -1)

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_operator_names(self):
    logging.debug("test_all_get_operator_names")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+COPN\r\n'}, {'OUT': b'+COPN: 1,\"FAKE1\"\r\n'},
                               {'OUT': b'+COPN: 2,\"FAKE 2\"\r\n'}, {'OUT': b'+COPN: 3,\"Fake Three\"\r\n'},
                               {'OUT': b'+COPN: DUMMY_ERROR\r\n'},{'OUT': b'DUMMY_ERROR\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getOperatorNames(), ["FAKE1", "FAKE 2", "Fake Three"])

    MockSerial.initializeMock([{'IN': b'AT+COPN\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getOperatorNames(), [])

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_neighbour_cells(self):
    logging.debug("test_all_get_neighbour_cells")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT^MONP\r\n'},
                               {'OUT': b'chann rs  dBm   PLMN   BCC C1 C2\r\n'},
                               {'OUT': b'504   18  -78   26203  1   27 28\r\n'},
                               {'OUT': b'505   19  -77   26204  2   28 29\r\n'},
                               {'OUT': b'Inva  lid param eters  he  r  e \r\n'}, # Invalid parameters
                               {'OUT': b'1     2   3     4      5\r\n'},         # Invalid number of parameters
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getNeighbourCells(), [{"chann": 504, "rs": 18, "dbm": -78, "plmn": 26203, "bcc": 1, "c1": 27, "c2": 28},
                                               {"chann": 505, "rs": 19, "dbm": -77, "plmn": 26204, "bcc": 2, "c1": 28, "c2": 29}])

    MockSerial.initializeMock([{'IN': b'AT^MONP\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getNeighbourCells(), [])

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_accumulated_call_meter(self):
    logging.debug("test_all_get_accumulated_call_meter")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CACM?\r\n'}, {'OUT': b'+CACM: FF05\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getAccumulatedCallMeter(), 0xFF05)

    MockSerial.initializeMock([{'IN': b'AT+CACM?\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getAccumulatedCallMeter(), -1)

    MockSerial.initializeMock([{'IN': b'AT+CACM?\r\n'}, {'OUT': b'+CACM: INVALID_NUMBER\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getAccumulatedCallMeter(), -1)

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_accumulated_call_meter_maximum(self):
    logging.debug("test_all_get_accumulated_call_meter_maximum")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CAMM?\r\n'}, {'OUT': b'+CAMM: FFFF\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getAccumulatedCallMeterMaximum(), 0xFFFF)

    MockSerial.initializeMock([{'IN': b'AT+CAMM?\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getAccumulatedCallMeterMaximum(), -1)

    MockSerial.initializeMock([{'IN': b'AT+CAMM?\r\n'}, {'OUT': b'+CAMM: INVALID_NUMBER\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getAccumulatedCallMeterMaximum(), -1)

  @patch('serial.Serial', new=MockSerial)
  def test_all_is_temperature_critical(self):
    logging.debug("test_all_is_temperature_critical")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT^SCTM?\r\n'}, {'OUT': b'^SCTM: DUMMY,0,OTHER_DUMMY\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.isTemperatureCritical(), False)

    MockSerial.initializeMock([{'IN': b'AT^SCTM?\r\n'}, {'OUT': b'^SCTM: DUMMY,1,OTHER_DUMMY\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.isTemperatureCritical(), True)

    MockSerial.initializeMock([{'IN': b'AT^SCTM?\r\n'}, {'OUT': b'^SCTM: DUMMY,INVALID_BOOL,OTHER_DUMMY\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.isTemperatureCritical(), False)

    MockSerial.initializeMock([{'IN': b'AT^SCTM?\r\n'}, {'OUT': b'^SCTM: DUMMY\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.isTemperatureCritical(), False)

    MockSerial.initializeMock([{'IN': b'AT^SCTM?\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.isTemperatureCritical(), False)

    MockSerial.initializeMock([{'IN': b'AT^SCTM?\r\n'}, {'OUT': b'+CAMM: INVALID_NUMBER\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.isTemperatureCritical(), False)

  @patch('serial.Serial', new=MockSerial)
  def test_all_set_internal_clock_to_current_date(self):
    logging.debug("test_all_set_internal_clock_to_current_date")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'^AT\+CCLK=\"[0-9]{2}\/[0-9]{2}\/[0-9]{2},[0-9]{2}:[0-9]{2}:[0-9]{2}\"\r\n$', 'mode': 'regex'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.setInternalClockToCurrentDate(), True)

    MockSerial.initializeMock([{'IN': b'^AT\+CCLK=\"[0-9]{2}\/[0-9]{2}\/[0-9]{2},[0-9]{2}:[0-9]{2}:[0-9]{2}\"\r\n$', 'mode': 'regex'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.setInternalClockToCurrentDate(), False)

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_internal_clock_date(self):
    logging.debug("test_all_get_internal_clock_date")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CCLK?\r\n'}, {'OUT': b'+CCLK: 11/12/13,14:15:16\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getDateFromInternalClock(), datetime.datetime.strptime("11/12/13,14:15:16", "%y/%m/%d,%H:%M:%S"))

    MockSerial.initializeMock([{'IN': b'AT+CCLK?\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getDateFromInternalClock(), -1)

    MockSerial.initializeMock([{'IN': b'AT+CCLK?\r\n'}, {'OUT': b'+CCLK: INVALID_DATE\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getDateFromInternalClock(), -1)

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_phonebook_entries(self):
    logging.debug("test_all_get_phonebook_entries")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CPBS="SM"\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-250),20,14\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBR=1,250\r\n'},
                               {'OUT': b'+CPBR: 1,"931123456",129,"Quentin Test"\r\n'},
                               {'OUT': b'+CPBR: 2,"9501234567",129,""\r\n'},
                               {'OUT': b'+CPBR: 4,"901234567",129,"Other"\r\n'},
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries("SM"), [{'contact_name': 'Quentin Test', 'index': 1, 'phone_number': '931123456'},
                                                     {'contact_name': '', 'index': 2, 'phone_number': '9501234567'},
                                                     {'contact_name': 'Other', 'index': 4, 'phone_number': '901234567'}])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-100),20,14\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBR=1,100\r\n'},
                               {'OUT': b'INVALID_LINE_BEFORE_RESULT...\r\n'},
                               {'OUT': b'+CPBR: 1,"931123456",129,"Quentin Test"\r\n'},
                               {'OUT': b'+CPBR: 2,"9501234567",129,""\r\n'},
                               {'OUT': b'+CPBR: 4,"901234567",129,"Other"\r\n'},
                               {'OUT': b'+CPBR: 7,"INVALID_NUMBER_OF_PARAM"\r\n'},
                               {'OUT': b'+CPBR: INVALID_INDEX,"901234567",129,"Other"\r\n'},
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [{'contact_name': 'Quentin Test', 'index': 1, 'phone_number': '931123456'},
                                                     {'contact_name': '', 'index': 2, 'phone_number': '9501234567'},
                                                     {'contact_name': 'Other', 'index': 4, 'phone_number': '901234567'}])

    MockSerial.initializeMock([{'IN': b'AT+CPBS="SM"\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(GSMTC35.GSMTC35.ePhonebookType.SIM), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (100-1),20,14\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (100)\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (NOT_NUMBER-1),20,14\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-NOT_NUMBER),20,14\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-100),NOT_NUMBER,14\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-100),20,NOT_NUMBER\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-100)\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-100),20\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-100),20,14\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBR=1,100\r\n'},  {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getPhonebookEntries(), [])

  @patch('serial.Serial', new=MockSerial)
  def test_all_add_phonebook_entry(self):
    logging.debug("test_all_add_phonebook_entry")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CPBS="ME"\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-250),20,14\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBW=,"+33601020304",145,"Test ADD"\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.addEntryToPhonebook(phone_number="+33601020304", contact_name="Test ADD", phonebook_type=GSMTC35.GSMTC35.ePhonebookType.GSM_MODULE))

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-250),20,14\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBW=,"0601020304",129,"Test ADD"\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.addEntryToPhonebook(phone_number="0601020304", contact_name="Test ADD"))

    MockSerial.initializeMock([{'IN': b'AT+CPBS="ME"\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.addEntryToPhonebook(phone_number="0601020304", contact_name="Test ADD", phonebook_type=GSMTC35.GSMTC35.ePhonebookType.GSM_MODULE))

    MockSerial.initializeMock([])
    self.assertFalse(gsm.addEntryToPhonebook(phone_number="", contact_name="Test ADD"))

    MockSerial.initializeMock([{'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-250),20,14\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertFalse(gsm.addEntryToPhonebook(phone_number="0601020304", contact_name="CONTACT NAME TOOOOOOOOOOOOOO LONG"))

  @patch('serial.Serial', new=MockSerial)
  def test_all_delete_phonebook_entry(self):
    logging.debug("test_all_delete_phonebook_entry")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CPBS="LD"\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBW=65\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.deleteEntryFromPhonebook(index=65, phonebook_type=GSMTC35.GSMTC35.ePhonebookType.LAST_DIALLING))

    MockSerial.initializeMock([{'IN': b'AT+CPBW=65\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.deleteEntryFromPhonebook(index=65))

    MockSerial.initializeMock([{'IN': b'AT+CPBS="LD"\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.deleteEntryFromPhonebook(index=65, phonebook_type=GSMTC35.GSMTC35.ePhonebookType.LAST_DIALLING))

  @patch('serial.Serial', new=MockSerial)
  def test_all_delete_all_phonebook_entries(self):
    logging.debug("test_all_delete_all_phonebook_entries")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CPBS="MC"\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-250),20,14\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBR=1,250\r\n'},
                               {'OUT': b'+CPBR: 1,"931123456",129,"Quentin Test"\r\n'},
                               {'OUT': b'+CPBR: 2,"9501234567",129,""\r\n'},
                               {'OUT': b'+CPBR: 4,"901234567",129,"Other"\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBW=1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBW=2\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBW=4\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.deleteAllEntriesFromPhonebook(phonebook_type=GSMTC35.GSMTC35.ePhonebookType.MISSED_CALLS))

    MockSerial.initializeMock([{'IN': b'AT+CPBS="MC"\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBR=?\r\n'}, {'OUT': b'+CPBR: (1-250),20,14\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBR=1,250\r\n'},
                               {'OUT': b'+CPBR: 1,"931123456",129,"Quentin Test"\r\n'},
                               {'OUT': b'+CPBR: 2,"9501234567",129,""\r\n'},
                               {'OUT': b'+CPBR: 4,"901234567",129,"Other"\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBW=1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPBW=2\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CPBW=4\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertFalse(gsm.deleteAllEntriesFromPhonebook(phonebook_type=GSMTC35.GSMTC35.ePhonebookType.MISSED_CALLS))

    MockSerial.initializeMock([{'IN': b'AT+CPBS="MC"\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.deleteAllEntriesFromPhonebook(phonebook_type=GSMTC35.GSMTC35.ePhonebookType.MISSED_CALLS))

  @patch('serial.Serial', new=MockSerial)
  def test_all_hang_up_call(self):
    logging.debug("test_all_hang_up_call")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.hangUpCall())

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'ATH\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.hangUpCall())

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'ATH\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.hangUpCall())

  @patch('serial.Serial', new=MockSerial)
  def test_all_pick_up_call(self):
    logging.debug("test_all_pick_up_call")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'ATA;\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.pickUpCall())

    MockSerial.initializeMock([{'IN': b'ATA;\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.pickUpCall())

  @patch('serial.Serial', new=MockSerial)
  def test_all_call(self):
    logging.debug("test_all_call")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'ATD0601020304;\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.call(phone_number="0601020304", hide_phone_number=False))

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'ATH\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'ATD0601020304;\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.call(phone_number="0601020304", hide_phone_number=False))

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'ATD#31#0601020304;\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.call(phone_number="0601020304", hide_phone_number=True))

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'ATH\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'ATD#31#0601020304;\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.call(phone_number="0601020304", hide_phone_number=True))

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'ATD0601020304;\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.call(phone_number="0601020304", hide_phone_number=False))

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'ATD#31#0601020304;\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.call(phone_number="0601020304", hide_phone_number=True))

  @patch('serial.Serial', new=MockSerial)
  def test_all_recall(self):
    logging.debug("test_all_recall")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'ATDL;\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.reCall())

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'ATH\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'ATDL;\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.reCall())

    MockSerial.initializeMock([{'IN': b'AT+CHUP\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'ATDL;\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.reCall())

  @patch('serial.Serial', new=MockSerial)
  def test_all_is_someone_calling(self):
    logging.debug("test_all_is_someone_calling")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CPAS\r\n'}, {'OUT': b'+CPAS: 3\r\n'}])
    self.assertTrue(gsm.isSomeoneCalling())

    MockSerial.initializeMock([{'IN': b'AT+CPAS\r\n'}, {'OUT': b'+CPAS: 4\r\n'}])
    self.assertFalse(gsm.isSomeoneCalling())

    MockSerial.initializeMock([{'IN': b'AT+CPAS\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.isSomeoneCalling())

  @patch('serial.Serial', new=MockSerial)
  def test_all_is_call_in_progress(self):
    logging.debug("test_all_is_call_in_progress")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CPAS\r\n'}, {'OUT': b'+CPAS: 4\r\n'}])
    self.assertTrue(gsm.isCallInProgress())

    MockSerial.initializeMock([{'IN': b'AT+CPAS\r\n'}, {'OUT': b'+CPAS: 3\r\n'}])
    self.assertFalse(gsm.isCallInProgress())

    MockSerial.initializeMock([{'IN': b'AT+CPAS\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.isCallInProgress())

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_last_call_duration(self):
    logging.debug("test_all_get_last_call_duration")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT^SLCD\r\n'}, {'OUT': b'^SLCD: 12:34:56\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getLastCallDuration(), 12*3600+34*60+56)

    MockSerial.initializeMock([{'IN': b'AT^SLCD\r\n'}, {'OUT': b'^SLCD: INVALID_TIME\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getLastCallDuration(), -1)

    MockSerial.initializeMock([{'IN': b'AT^SLCD\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getLastCallDuration(), -1)

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_current_call_state(self):
    logging.debug("test_all_get_current_call_state")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CLCC\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getCurrentCallState(), (GSMTC35.GSMTC35.eCall.NOCALL, ''))

    MockSerial.initializeMock([{'IN': b'AT+CLCC\r\n'}, {'OUT': b'+CLCC: 1,1,5,0,0,"+33601020304",145\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getCurrentCallState(), (GSMTC35.GSMTC35.eCall.WAITING, '+33601020304'))

    MockSerial.initializeMock([{'IN': b'AT+CLCC\r\n'}, {'OUT': b'+CLCC: 1,1,4,0,0,"+33601020304",145\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getCurrentCallState(), (GSMTC35.GSMTC35.eCall.INCOMING, '+33601020304'))

    MockSerial.initializeMock([{'IN': b'AT+CLCC\r\n'}, {'OUT': b'+CLCC: 1,1,3,0,0,"+33601020304",145\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getCurrentCallState(), (GSMTC35.GSMTC35.eCall.ALERTING, '+33601020304'))

    MockSerial.initializeMock([{'IN': b'AT+CLCC\r\n'}, {'OUT': b'+CLCC: 1,1,2,0,0,"+33601020304",145\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getCurrentCallState(), (GSMTC35.GSMTC35.eCall.DIALING, '+33601020304'))

    MockSerial.initializeMock([{'IN': b'AT+CLCC\r\n'}, {'OUT': b'+CLCC: 1,1,1,0,0,"+33601020304",145\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getCurrentCallState(), (GSMTC35.GSMTC35.eCall.HELD, '+33601020304'))

    MockSerial.initializeMock([{'IN': b'AT+CLCC\r\n'}, {'OUT': b'+CLCC: 1,1,0,0,0,"+33601020304",145\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getCurrentCallState(), (GSMTC35.GSMTC35.eCall.ACTIVE, '+33601020304'))

    MockSerial.initializeMock([{'IN': b'AT+CLCC\r\n'}, {'OUT': b'+CLCC: INVALID_LIST,A,B,C,D\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getCurrentCallState(), (GSMTC35.GSMTC35.eCall.NOCALL, ''))

    MockSerial.initializeMock([{'IN': b'AT+CLCC\r\n'}, {'OUT': b'+CLCC: INVALID_LIST\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getCurrentCallState(), (GSMTC35.GSMTC35.eCall.NOCALL, ''))

  @patch('serial.Serial', new=MockSerial)
  def test_all_set_forward_status(self):
    logging.debug("test_all_set_forward_status")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,3,+33601020304,145,1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.UNCONDITIONAL, GSMTC35.GSMTC35.eForwardClass.VOICE, True, "+33601020304"))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,4,,,1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.UNCONDITIONAL, GSMTC35.GSMTC35.eForwardClass.VOICE, False))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=1,4,,,2\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.MOBILE_BUSY, GSMTC35.GSMTC35.eForwardClass.DATA, False))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=2,4,,,4\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.NO_REPLY, GSMTC35.GSMTC35.eForwardClass.FAX, False))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=3,4,,,8\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.NOT_REACHABLE, GSMTC35.GSMTC35.eForwardClass.SMS, False))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=4,4,,,16\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.ALL_CALL_FORWARDING, GSMTC35.GSMTC35.eForwardClass.DATA_CIRCUIT_SYNC, False))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=5,4,,,32\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.ALL_CONDITIONAL_CALL_FORWARDING, GSMTC35.GSMTC35.eForwardClass.DATA_CIRCUIT_ASYNC, False))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=5,4,,,64\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.ALL_CONDITIONAL_CALL_FORWARDING, GSMTC35.GSMTC35.eForwardClass.DEDICATED_PACKED_ACCESS, False))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=5,4,,,128\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.ALL_CONDITIONAL_CALL_FORWARDING, GSMTC35.GSMTC35.eForwardClass.DEDICATED_PAD_ACCESS, False))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,3,+33601020304,145,1\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.UNCONDITIONAL, GSMTC35.GSMTC35.eForwardClass.VOICE, True, "+33601020304"))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,4,,,1\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.setForwardStatus(GSMTC35.GSMTC35.eForwardReason.UNCONDITIONAL, GSMTC35.GSMTC35.eForwardClass.VOICE, False))

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_forward_status(self):
    logging.debug("test_all_get_forward_status")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,2\r\n'},
                               {'OUT': b'+CCFC: 0,2\r\n'}, {'OUT': b'+CCFC: 0,1\r\n'}, {'OUT': b'+CCFC: 0,4\r\n'},
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getForwardStatus(), [{'class': 'DATA', 'enabled': False},
                                              {'class': 'VOICE', 'enabled': False},
                                              {'class': 'FAX', 'enabled': False}
                                             ])

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,2\r\n'},
                               {'OUT': b'+CCFC: 1,2,+33601020304,145\r\n'},
                               {'OUT': b'+CCFC: 1,1,0601020304,129\r\n'},
                               {'OUT': b'+CCFC: 0,4\r\n'},
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getForwardStatus(), [{'class': 'DATA', 'enabled': True, 'is_international': True, 'phone_number': '+33601020304'},
                                              {'class': 'VOICE', 'enabled': True, 'is_international': False, 'phone_number': '0601020304'},
                                              {'class': 'FAX', 'enabled': False}
                                             ])

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,2\r\n'},
                               {'OUT': b'+CCFC: 1,1\r\n'}, {'OUT': b'+CCFC: 0,2\r\n'}, {'OUT': b'+CCFC: 1,4\r\n'},
                               {'OUT': b'+CCFC: 0,8\r\n'}, {'OUT': b'+CCFC: 1,16\r\n'}, {'OUT': b'+CCFC: 0,32\r\n'},
                               {'OUT': b'+CCFC: 1,64\r\n'}, {'OUT': b'+CCFC: 0,128\r\n'},
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getForwardStatus(), [{'class': 'VOICE', 'enabled': True},
                                              {'class': 'DATA', 'enabled': False},
                                              {'class': 'FAX', 'enabled': True},
                                              {'class': 'SMS', 'enabled': False},
                                              {'class': 'DATA_CIRCUIT_SYNC', 'enabled': True},
                                              {'class': 'DATA_CIRCUIT_ASYNC', 'enabled': False},
                                              {'class': 'DEDICATED_PACKED_ACCESS', 'enabled': True},
                                              {'class': 'DEDICATED_PAD_ACCESS', 'enabled': False}])

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,2\r\n'},
                               {'OUT': b'+CCFC: INVALID_LIST\r\n'},
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getForwardStatus(), [])

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,2\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getForwardStatus(), [])

    MockSerial.initializeMock([{'IN': b'AT+CCFC=0,2\r\n'}, {'OUT': b'INVALID_DATA\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getForwardStatus(), [])

  @patch('serial.Serial', new=MockSerial)
  def test_all_lock_sim_pin(self):
    logging.debug("test_all_lock_sim_pin")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CLCK="SC",1,1234\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.lockSimPin("1234"))

    MockSerial.initializeMock([{'IN': b'AT+CLCK="SC",1,4321\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.lockSimPin(4321))

    MockSerial.initializeMock([{'IN': b'AT+CLCK="SC",1,4321\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.lockSimPin(4321))

  @patch('serial.Serial', new=MockSerial)
  def test_all_unlock_sim_pin(self):
    logging.debug("test_all_unlock_sim_pin")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CLCK="SC",0,1234\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.unlockSimPin("1234"))

    MockSerial.initializeMock([{'IN': b'AT+CLCK="SC",0,4321\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.unlockSimPin(4321))

    MockSerial.initializeMock([{'IN': b'AT+CLCK="SC",0,4321\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.unlockSimPin(4321))

  @patch('serial.Serial', new=MockSerial)
  def test_all_change_pin(self):
    logging.debug("test_all_change_pin")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CLCK="SC",1,1234\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPWD="SC","1234","4321"\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.changePin(old_pin="1234", new_pin="4321"))

    MockSerial.initializeMock([{'IN': b'AT+CLCK="SC",1,1234\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.changePin(old_pin="1234", new_pin="4321"))

    MockSerial.initializeMock([{'IN': b'AT+CLCK="SC",1,1234\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CPWD="SC","1234","4321"\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.changePin(old_pin="1234", new_pin="4321"))

  @patch('serial.Serial', new=MockSerial)
  def test_all_is_in_sleep_mode(self):
    logging.debug("test_all_is_in_sleep_mode")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # In real case scenario in sleep mode, the gsm doesn't answer anything
    MockSerial.initializeMock([{'IN': b'AT+CFUN?\r\n'}])
    self.assertTrue(gsm.isInSleepMode())

    # In real case scenario in not sleep mode, the gsm answers "+CFUN: 1"
    MockSerial.initializeMock([{'IN': b'AT+CFUN?\r\n'}, {'OUT': b'+CFUN: 1\r\n'},
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},])
    self.assertFalse(gsm.isInSleepMode())

    # This case should never happen but who knows (GSM answering it is sleeping)...
    MockSerial.initializeMock([{'IN': b'AT+CFUN?\r\n'}, {'OUT': b'+CFUN: 0\r\n'},
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},])
    self.assertTrue(gsm.isInSleepMode())

    MockSerial.initializeMock([{'IN': b'AT+CFUN?\r\n'}, {'OUT': b'+CFUN: INVALID_RESPONSE\r\n'},
                               {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},])
    self.assertFalse(gsm.isInSleepMode())

    MockSerial.initializeMock([{'IN': b'AT+CFUN?\r\n'}, {'OUT': b'+CFUN: \r\n'}])
    self.assertFalse(gsm.isInSleepMode())

  @patch('serial.Serial', new=MockSerial)
  def test_all_sleep(self):
    logging.debug("test_all_sleep")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # Not waiting gsm to wake up
    MockSerial.initializeMock([{'IN': b'AT+CLIP=1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CFUN=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_call=True, blocking=False), (True, False, False, False, False))

    # Waiting call received
    MockSerial.initializeMock([{'IN': b'AT+CLIP=1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CFUN=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT\r\n'},
                               {'OUT': b'+CLIP\r\n', 'wait_ms': 3000},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_call=True), (True, False, True, False, False))

    # Waiting gsm alarm received
    MockSerial.initializeMock([{'IN': b'AT+CCLK?\r\n'}, {'OUT': b'+CCLK: 10/10/10,10:10:10\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CALA="10/10/10,10:10:21",0,0,"SLEEP"\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CFUN=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT\r\n'},
                               {'OUT': b'+CALA\r\n', 'wait_ms': 3000},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_timer_in_sec=10), (True, True, False, False, False))

    # Waiting sms received
    MockSerial.initializeMock([{'IN': b'AT+CNMI=1,1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CFUN=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT\r\n'},
                               {'OUT': b'+CMTI\r\n', 'wait_ms': 3000},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_sms=True), (True, False, False, True, False))

    # Waiting sms received
    MockSerial.initializeMock([{'IN': b'AT^SCTM=1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CFUN=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT\r\n'},
                               {'OUT': b'^SCTM\r\n', 'wait_ms': 3000},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_temperature_warning=True), (True, False, False, False, True))

    # Already alive
    MockSerial.initializeMock([{'IN': b'AT\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.waitEndOfSleepMode(), (True, False, False, False, False))

    # Invalid parameters
    MockSerial.initializeMock([])
    self.assertEqual(gsm.sleep(), (False, False, False, False, False))

    # No wake up specified
    MockSerial.initializeMock([{'IN': b'AT\r\n'}, {'OUT': b'HEY THERE, I\'M UP!\r\n', 'wait_ms': 3000},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.sleep(), (False, False, False, False, False))

    # Error while setting up wake up request
    MockSerial.initializeMock([{'IN': b'AT^SCTM=1\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_temperature_warning=True), (False, False, False, False, False))

    MockSerial.initializeMock([{'IN': b'AT+CNMI=1,1\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_sms=True), (False, False, False, False, False))

    MockSerial.initializeMock([{'IN': b'AT+CLIP=1\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_call=True), (False, False, False, False, False))

    MockSerial.initializeMock([{'IN': b'AT+CNMI=1,1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CFUN=0\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_sms=10), (False, False, False, False, False))

    MockSerial.initializeMock([{'IN': b'AT+CCLK?\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CLIP=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CNMI=0,0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT^SCTM=0\r\n'}, {'OUT': b'OK\r\n'}
                               ])
    self.assertEqual(gsm.sleep(wake_up_with_timer_in_sec=10), (False, False, False, False, False))

    # Error during waking up
    MockSerial.initializeMock([{'IN': b'AT\r\n'}])
    self.assertEqual(gsm.waitEndOfSleepMode(max_additional_waiting_time_in_sec=1), (False, False, False, False, False))

  def test_all_enum_conversion(self):
    logging.debug("test_all_enum_conversion")

    # eCallToString
    self.assertEqual(GSMTC35.GSMTC35.eCallToString(GSMTC35.GSMTC35.eCall.NOCALL), "NOCALL")
    self.assertEqual(GSMTC35.GSMTC35.eCallToString(GSMTC35.GSMTC35.eCall.ACTIVE), "ACTIVE")
    self.assertEqual(GSMTC35.GSMTC35.eCallToString(GSMTC35.GSMTC35.eCall.HELD), "HELD")
    self.assertEqual(GSMTC35.GSMTC35.eCallToString(GSMTC35.GSMTC35.eCall.DIALING), "DIALING")
    self.assertEqual(GSMTC35.GSMTC35.eCallToString(GSMTC35.GSMTC35.eCall.ALERTING), "ALERTING")
    self.assertEqual(GSMTC35.GSMTC35.eCallToString(GSMTC35.GSMTC35.eCall.INCOMING), "INCOMING")
    self.assertEqual(GSMTC35.GSMTC35.eCallToString(GSMTC35.GSMTC35.eCall.WAITING), "WAITING")
    self.assertEqual(GSMTC35.GSMTC35.eCallToString(-98), "UNDEFINED")

    # eForwardClassToString
    self.assertEqual(GSMTC35.GSMTC35.eForwardClassToString(GSMTC35.GSMTC35.eForwardClass.VOICE), "VOICE")
    self.assertEqual(GSMTC35.GSMTC35.eForwardClassToString(GSMTC35.GSMTC35.eForwardClass.DATA), "DATA")
    self.assertEqual(GSMTC35.GSMTC35.eForwardClassToString(GSMTC35.GSMTC35.eForwardClass.FAX), "FAX")
    self.assertEqual(GSMTC35.GSMTC35.eForwardClassToString(GSMTC35.GSMTC35.eForwardClass.SMS), "SMS")
    self.assertEqual(GSMTC35.GSMTC35.eForwardClassToString(GSMTC35.GSMTC35.eForwardClass.DATA_CIRCUIT_SYNC), "DATA_CIRCUIT_SYNC")
    self.assertEqual(GSMTC35.GSMTC35.eForwardClassToString(GSMTC35.GSMTC35.eForwardClass.DATA_CIRCUIT_ASYNC), "DATA_CIRCUIT_ASYNC")
    self.assertEqual(GSMTC35.GSMTC35.eForwardClassToString(GSMTC35.GSMTC35.eForwardClass.DEDICATED_PACKED_ACCESS), "DEDICATED_PACKED_ACCESS")
    self.assertEqual(GSMTC35.GSMTC35.eForwardClassToString(GSMTC35.GSMTC35.eForwardClass.DEDICATED_PAD_ACCESS), "DEDICATED_PAD_ACCESS")
    self.assertEqual(GSMTC35.GSMTC35.eForwardClassToString(-456), "UNDEFINED")

    # eForwardReasonToString
    self.assertEqual(GSMTC35.GSMTC35.eForwardReasonToString(GSMTC35.GSMTC35.eForwardReason.UNCONDITIONAL), "UNCONDITIONAL")
    self.assertEqual(GSMTC35.GSMTC35.eForwardReasonToString(GSMTC35.GSMTC35.eForwardReason.MOBILE_BUSY), "MOBILE_BUSY")
    self.assertEqual(GSMTC35.GSMTC35.eForwardReasonToString(GSMTC35.GSMTC35.eForwardReason.NO_REPLY), "NO_REPLY")
    self.assertEqual(GSMTC35.GSMTC35.eForwardReasonToString(GSMTC35.GSMTC35.eForwardReason.NOT_REACHABLE), "NOT_REACHABLE")
    self.assertEqual(GSMTC35.GSMTC35.eForwardReasonToString(GSMTC35.GSMTC35.eForwardReason.ALL_CALL_FORWARDING), "ALL_CALL_FORWARDING")
    self.assertEqual(GSMTC35.GSMTC35.eForwardReasonToString(GSMTC35.GSMTC35.eForwardReason.ALL_CONDITIONAL_CALL_FORWARDING), "ALL_CONDITIONAL_CALL_FORWARDING")
    self.assertEqual(GSMTC35.GSMTC35.eForwardReasonToString(-589), "UNDEFINED")

  @patch('serial.Serial', new=MockSerial)
  def test_success_send_sms_7bit(self):
    logging.debug("test_success_send_sms_7bit")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # One part 7 bit SMS with extended alphabet
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=36\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203F400001AC2F03C3D06DD40E2341D346D4E41657CB80D6797419B32\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'+CMGS: 59\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Basic 7 bit SMS example €", network_delay_sec=0))

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=36\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203F400001AC2F03C3D06DD40E2341D346D4E41657CB80D6797419B32\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'+CMGS: 59\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Basic 7 bit SMS example €", network_delay_sec=0))

    # Multipart 7 bit SMS with extended alphabet
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=140\r\n'}, {'IN': b'^0041[0-9A-F]{2}0B913306010203F4000091050003[0-9A-F]{2}02019A75363D0D0FCBE9A01B489CA683A6CD29A88C0FB7E1EC32685376B95C2E97CBE572B9402E97CBE572B95C2E17C8E572B95C2E97CBE502B95C2E97CBE572B95C2097CBE572B95C2E970BE472B95C2E97CBE572815C2E97CBE572B95C2E90CBE572B95C2E97CB0572B95C2E97CBE572B9402E97CBE572B95C2E\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=33\r\n'}, {'IN': b'^0041[0-9A-F]{2}0B913306010203F4000016050003[0-9A-F]{2}02025C2097CBE572B95C2E97ABE82402\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Multipart 7 bit SMS example €.......... .......... .......... .......... .......... .......... .......... .......... .......... .......... ..........END", network_delay_sec=0))

    # One part 7 bit SMS with base alphabet
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=34\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203F4000017C2F03C3D06DD40E2341D346D4E41657CB80D679701\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'+CMGS: 59\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Basic 7 bit SMS example", network_delay_sec=0))

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=34\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203F4000017C2F03C3D06DD40E2341D346D4E41657CB80D679701\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'+CMGS: 59\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Basic 7 bit SMS example", network_delay_sec=0))

    # Multipart 7 bit SMS with base alphabet
    # This test also check robustness of the lib when receiving dirty char without end of line
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=140\r\n'}, {'IN': b'^0041[0-9A-F]{2}0B913306010203F4000091050003[0-9A-F]{2}02019A75363D0D0FCBE9A01B489CA683A6CD29A88C0FB7E1EC32C8E572B95C2E97CBE502B95C2E97CBE572B95C2097CBE572B95C2E970BE472B95C2E97CBE572815C2E97CBE572B95C2E90CBE572B95C2E97CB0572B95C2E97CBE572B9402E97CBE572B95C2E17C8E572B95C2E97CBE502B95C2E97CBE572B95C20\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'InvalidChar'}, {'OUT': b'', 'wait_ms': 3000}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=31\r\n'}, {'IN': b'^0041[0-9A-F]{2}0B913306010203F4000014050003[0-9A-F]{2}02025C2E97CBE572B95CAEA29308\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'', 'wait_ms': 3000}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Multipart 7 bit SMS example .......... .......... .......... .......... .......... .......... .......... .......... .......... .......... ..........END", network_delay_sec=0))

  @patch('serial.Serial', new=MockSerial)
  def test_failed_send_sms_7bit(self):
    logging.debug("test_failed_send_sms_7bit")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # Error sent by GSM
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=36\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203F400001AC2F03C3D06DD40E2341D346D4E41657CB80D6797419B32\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'+CMGS: 59\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertFalse(gsm.sendSMS(phone_number="+33601020304", msg="Basic 7 bit SMS example €", network_delay_sec=0))

    # Impossible to write data to serial port
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=36\r\n'}])
    self.assertFalse(gsm.sendSMS(phone_number="+33601020304", msg="Basic 7 bit SMS example €", network_delay_sec=0))

    # Send empty SMS
    MockSerial.initializeMock([])
    self.assertFalse(gsm.sendSMS(phone_number="+33601020304", msg="", network_delay_sec=0))

    # Send to empty phone number
    MockSerial.initializeMock([])
    self.assertFalse(gsm.sendSMS(phone_number="", msg="Hi", network_delay_sec=0))

    # No communication with GSM
    MockSerial.initializeMock([])
    self.assertFalse(gsm.sendSMS(phone_number="+33601020304", msg="Hi", network_delay_sec=0))

  @patch('serial.Serial', new=MockSerial)
  def test_success_send_sms_ucs2(self):
    logging.debug("test_success_send_sms_ucs2")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # One part UCS2 SMS
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=45\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203F4000820004E006F00740020003700620069007400200063006800610072003A002000B0\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'+CMGS: 45\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Not 7bit char: °", network_delay_sec=0))

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=45\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203F4000820004E006F00740020003700620069007400200063006800610072003A002000B0\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'+CMGS: 45\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Not 7bit char: °", network_delay_sec=0))

    # Multipart UCS2 SMS
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=153\r\n'}, {'IN': b'^0041[0-9A-F]{2}0B913306010203F400088C050003[0-9A-F]{2}0201004E006F00740020003700620069007400200063006800610072003A002000B0002E002E002E002E002E002E002E002E002E002E0020002E002E002E002E002E002E002E002E0020002E002E002E002E002E002E002E002E0020002E002E002E002E002E002E002E002E0020002E002E002E002E002E002E002E002E0020002E002E002E002E\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=37\r\n'}, {'IN': b'^0041[0-9A-F]{2}0B913306010203F4000818050003[0-9A-F]{2}0202002E002E002E002E002E002E0045004E0044\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Not 7bit char: °.......... ........ ........ ........ ........ ..........END", network_delay_sec=0))

  @patch('serial.Serial', new=MockSerial)
  def test_failed_send_sms_ucs2(self):
    logging.debug("test_failed_send_sms_ucs2")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS=45\r\n'}, {'IN': b'^0001[0-9A-F]{2}0B913306010203F4000820004E006F00740020003700620069007400200063006800610072003A002000B0\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertFalse(gsm.sendSMS(phone_number="+33601020304", msg="Not 7bit char: °"))

  @patch('serial.Serial', new=MockSerial)
  def test_success_send_sms_text_mode(self):
    logging.debug("test_success_send_sms_text_mode")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # One 7 bits SMS: wanted to use PDU mode but not possible so using text mode (fallback)
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'^Text mode SMS\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Text mode SMS", network_delay_sec=0))

    # One 7 bits SMS in text mode (< 70 bytes)
    MockSerial.initializeMock([{'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'^Text mode SMS\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Text mode SMS", network_delay_sec=0, force_text_mode=True))

    # One 7 bits SMS in text mode (> 70 bytes)
    MockSerial.initializeMock([{'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'^Text mode SMS .......... .......... .......... .......... .......... .......... ..........\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Text mode SMS .......... .......... .......... .......... .......... .......... ..........", network_delay_sec=0, force_text_mode=True))

    # Multiple 7 bits SMS (NOT MMS because not possible) in text mode
    MockSerial.initializeMock([{'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'^Text mode multiple SMS .......... .......... .......... .......... .......... .......... .......... .......... .......... .......... .......\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'^...\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Text mode multiple SMS .......... .......... .......... .......... .......... .......... .......... .......... .......... .......... ..........", network_delay_sec=0, force_text_mode=True))

    # Multiple UCS2 SMS (NOT MMS because not possible) in text mode
    MockSerial.initializeMock([{'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'^Text mode multiple SMS\xc2\xb0 .......... .......... .......... .......... ..\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'^........ ..........\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.sendSMS(phone_number="+33601020304", msg="Text mode multiple SMS° .......... .......... .......... .......... .......... ..........", network_delay_sec=0, force_text_mode=True))

  @patch('serial.Serial', new=MockSerial)
  def test_failed_send_sms_text_mode(self):
    logging.debug("test_failed_send_sms_text_mode")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CMGS="+33601020304"\r\n'}, {'IN': b'^Text mode SMS\x1a$', 'mode': 'regex'},
                               {'OUT': b'\r\n'}, {'OUT': b'>'}, {'OUT': b'\r\n'}, {'OUT': b'\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertFalse(gsm.sendSMS(phone_number="+33601020304", msg="Text mode SMS", network_delay_sec=0))

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_sms_all_type(self):
    logging.debug("test_all_get_sms_all_type")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=0\r\n'},
                               {'OUT': b'+CMGL: 9,0,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(sms_type=GSMTC35.GSMTC35.eSMS.UNREAD_SMS, waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'REC UNREAD', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=1\r\n'},
                               {'OUT': b'+CMGL: 9,1,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(sms_type=GSMTC35.GSMTC35.eSMS.READ_SMS, waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'REC READ', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=2\r\n'},
                               {'OUT': b'+CMGL: 9,2,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(sms_type=GSMTC35.GSMTC35.eSMS.UNSENT_SMS, waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'STO UNSENT', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=3\r\n'},
                               {'OUT': b'+CMGL: 9,3,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(sms_type=GSMTC35.GSMTC35.eSMS.SENT_SMS, waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'STO SENT', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'+CMGL: 9,0,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(sms_type=GSMTC35.GSMTC35.eSMS.ALL_SMS, waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'REC UNREAD', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'+CMGL: 9,0,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(sms_type=-546, waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'REC UNREAD', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'+CMGL: 9,0,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(sms_type="4", waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'REC UNREAD', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=3\r\n'},
                               {'OUT': b'+CMGL: 9,3,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(sms_type="3", waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'STO SENT', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'+CMGL: 9,ALL,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'ALL', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'+CMGL: 9,REC READ,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'REC READ', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'+CMGL: 9,4,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'ALL', 'time': '10:37:32 GMT+1.0'}])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'+CMGL: 9,UNDEFINED,,39\r\n'},
                               {'OUT': b'07911326040011F5240B911326880736F40000111081017323401654747A0E4ACF41F4329E0E6A97E7F3F0B90C9201\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0), [{'charset': '7bit', 'date': '11/01/18', 'index': 9, 'phone_number': '+31628870634', 'phone_number_type': 145, 'service_center_phone_number': '31624000115', 'service_center_type': 145, 'sms': 'This is text message 2', 'sms_encoded': '546869732069732074657874206D6573736167652032', 'status': 'ALL', 'time': '10:37:32 GMT+1.0'}])

  @patch('serial.Serial', new=MockSerial)
  def test_all_get_sms_text_mode(self):
    logging.debug("test_all_get_sms_text_mode")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # No SMS
    MockSerial.initializeMock([{'IN': b'AT+CMGL="ALL"\r\n'},
                               {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(force_text_mode=True, waiting_time_sec=0),[])

    # 2 SMS
    MockSerial.initializeMock([{'IN': b'AT+CMGL="ALL"\r\n'},
                               {'OUT': b'+CMGL: 1,"REC UNREAD","+31628870634",,"11/01/09,10:26:26+04"\r\n'},
                               {'OUT': b'This is text message 1\r\n'},
                               {'OUT': b'+CMGL: 2,"REC UNREAD","+31628870634",,"11/01/09,10:26:49+04"\r\n'},
                               {'OUT': b'This is text message 2\r\n'},
                               {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(force_text_mode=True, waiting_time_sec=0),
                      [
                        {
                          'charset': 'TC35TextModeInconsistentCharset', 'date': '11/01/09', 'index': 1,
                          'phone_number': '+31628870634', 'sms': 'This is text message 1', 'status': 'REC UNREAD',
                          'time': '10:26:26+04'
                        },
                        {
                          'charset': 'TC35TextModeInconsistentCharset', 'date': '11/01/09', 'index': 2,
                          'phone_number': '+31628870634', 'sms': 'This is text message 2', 'status': 'REC UNREAD',
                          'time': '10:26:49+04'
                        }
                      ]
                    )

    # Fallback to text mode because pdu mode failed
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CMGL="ALL"\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0),[])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CMGL="ALL"\r\n'},
                               {'OUT': b'+CMGL: 1,"REC UNREAD","+31628870634",,"11/01/09,10:26:26+04"\r\n'},
                               {'OUT': b'This is text message 1\r\n'},
                               {'OUT': b'+CMGL: 2,"REC UNREAD","+31628870634",,"11/01/09,10:26:49+04"\r\n'},
                               {'OUT': b'This is text message 2\r\n'},
                               {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0),
                      [
                        {
                          'charset': 'TC35TextModeInconsistentCharset', 'date': '11/01/09', 'index': 1,
                          'phone_number': '+31628870634', 'sms': 'This is text message 1', 'status': 'REC UNREAD',
                          'time': '10:26:26+04'
                        },
                        {
                          'charset': 'TC35TextModeInconsistentCharset', 'date': '11/01/09', 'index': 2,
                          'phone_number': '+31628870634', 'sms': 'This is text message 2', 'status': 'REC UNREAD',
                          'time': '10:26:49+04'
                        }
                      ]
                    )

  @patch('serial.Serial', new=MockSerial)
  def test_success_get_sms_7bit_8bit_ucs2(self):
    logging.debug("test_success_get_sms_7bit_8bit_ucs2")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # Receiving Normal SMS + Extended in 7 bit and ucs2 (and 8 bit) SMS
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=0\r\n'},
                               # 7 bit normal SMS
                               {'OUT': b'+CMGL: 1,0,,35\r\n'},
                               {'OUT': b'07913396050046F6040B913306048216F100009111601043304012C2F03C3D06DD40E2347D0E9A36A7A010\r\n'},
                               # 7 bit normal SMS (extended table)
                               {'OUT': b'+CMGL: 7,0,,53\r\n'},
                               {'OUT': b'07913396050036F9040B913306048216F100009111602061244026C2F03C3D06DD40E2341D346FCF41F7341D0D2AE3E96537B94C06D1C3627619B42903\r\n'},
                               # 7 bit extended SMS
                               {'OUT': b'+CMGL: 3,0,,159\r\n'},
                               {'OUT': b'07913396050036F8440B913306048216F1000091116010631340A00500033202018A787AD94D2E93413790384D074D9B5310AAD99CA640A15028140A815C2E97CBE572B95C2E97CBE572B95C2E90CBE572B95C2E97CBE572B95C2E97CBE572815C2E97CBE572B95C2E97CBE572B95C2E97CBE502B95C2E97CBE572B95C2E97CBE572B95C2097CBE572B95C2E97CBE572B95C2E97CBE572B95C2E97CBE502B95C2E97CBE572B95C\r\n'},
                               {'OUT': b'+CMGL: 4,0,,46\r\n'},
                               {'OUT': b'07913396050036F8440B913306048216F10000911160106323401E0500033202025C2E97ABE8244ECBE3B79B0C8287E57410BA2C2F03\r\n'},
                               # UCS2 normal SMS
                               {'OUT': b'+CMGL: 2,0,,63\r\n'},
                               {'OUT': b'07913396050046F4040B913306048216F10008911160104345402C004200610073006900630020005500430053003200200053004D0053002000210020007C00B0002E00B0007C\r\n'},
                               # UCS2 extended SMS
                               {'OUT': b'+CMGL: 5,0,,159\r\n'},
                               {'OUT': b'07913396050036F6440B913306048216F10008911160107393408C0500033302010045007800740065006E0064006500640020005500430053003200200053004D005300200028004D004D005300290020007C00B0002E00B0007C0020002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E0020002E002E002E002E002E002E002E\r\n'},
                               {'OUT': b'+CMGL: 6,0,,75\r\n'},
                               {'OUT': b'07913396050036F6440B913306048216F1000891116010730440380500033302020045004E0044005300650063006F006E00640020007000610072007400200068006500720065002000B0003D00B000200021\r\n'},
                               # 8 bit normal SMS
                               # TODO: I have no example of 8 bit SMS, feel free to send it to me if you have one !
                               # 8 bit extended SMS
                               # TODO: I have no example of 8 bit MMS, feel free to send it to me if you have one !
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getSMS(sms_type=GSMTC35.GSMTC35.eSMS.UNREAD_SMS, waiting_time_sec=0),
                     [
                       {
                         'index': 1, 'status': 'REC UNREAD', 'service_center_type': 145, 'service_center_phone_number': '33695000646', 'phone_number_type': 145,
                         'phone_number': '+33604028611', 'date': '19/11/06', 'time': '01:34:03 GMT+1.0', 'charset': '7bit',
                         'sms': 'Basic 7 bits SMS !',
                         'sms_encoded': '42617369632037206269747320534D532021'
                       },
                       {
                         'index': 7, 'status': 'REC UNREAD', 'service_center_type': 145, 'service_center_phone_number': '33695000639', 'phone_number_type': 145,
                         'phone_number': '+33604028611', 'date': '19/11/06', 'time': '02:16:42 GMT+1.0', 'charset': '7bit',
                         'sms': 'Basic 7 bit sms with extended table €',
                         'sms_encoded': '426173696320372062697420736D73207769746820657874656E646564207461626C6520E282AC'
                       },
                       {'index': 3, 'status': 'REC UNREAD', 'service_center_type': 145,
                         'service_center_phone_number': '33695000638', 'phone_number_type': 145, 'phone_number': '+33604028611', 'date': '19/11/06',
                         'time': '01:36:31 GMT+1.0', 'charset': '7bit', 'header_iei': 0, 'header_ie_data': '320201', 'header_multipart_ref_id': 50,
                         'header_multipart_nb_of_part': 2, 'header_multipart_current_part_nb': 1,
                         'sms': 'Extended 7 bit SMS (MMS) !!!!!! .................. .................... ...................... .................. ............................ ..........',
                         'sms_encoded': '457874656E64656420372062697420534D5320284D4D532920212121212121202E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E202E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E202E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E202E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E202E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E2E202E2E2E2E2E2E2E2E2E2E'
                       },
                       {
                         'index': 4, 'status': 'REC UNREAD', 'service_center_type': 145, 'service_center_phone_number': '33695000638',
                         'phone_number_type': 145, 'phone_number': '+33604028611', 'date': '19/11/06', 'time': '01:36:32 GMT+1.0',
                         'charset': '7bit', 'header_iei': 0, 'header_ie_data': '320202', 'header_multipart_ref_id': 50,
                         'header_multipart_nb_of_part': 2, 'header_multipart_current_part_nb': 2,
                         'sms': '....ENDSecond part here',
                         'sms_encoded': '2E2E2E2E454E445365636F6E6420706172742068657265'
                       },
                       {
                         'index': 2, 'status': 'REC UNREAD', 'service_center_type': 145, 'service_center_phone_number': '33695000644', 'phone_number_type': 145,
                         'phone_number': '+33604028611', 'date': '19/11/06', 'time': '01:34:54 GMT+1.0', 'charset': 'utf16-be',
                         'sms': 'Basic UCS2 SMS ! |°.°|',
                         'sms_encoded': '4200610073006900630020005500430053003200200053004D0053002000210020007C00B0002E00B0007C'
                       },
                       {
                         'index': 5, 'status': 'REC UNREAD', 'service_center_type': 145, 'service_center_phone_number': '33695000636', 'phone_number_type': 145,
                         'phone_number': '+33604028611', 'date': '19/11/06', 'time': '01:37:39 GMT+1.0', 'charset': 'utf16-be', 'header_iei': 0,
                         'header_ie_data': '330201', 'header_multipart_ref_id': 51, 'header_multipart_nb_of_part': 2, 'header_multipart_current_part_nb': 1,
                         'sms': 'Extended UCS2 SMS (MMS) |°.°| ............................. .......',
                         'sms_encoded': '0045007800740065006E0064006500640020005500430053003200200053004D005300200028004D004D005300290020007C00B0002E00B0007C0020002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E0020002E002E002E002E002E002E002E'
                       },
                       {
                         'index': 6, 'status': 'REC UNREAD', 'service_center_type': 145, 'service_center_phone_number': '33695000636', 'phone_number_type': 145,
                         'phone_number': '+33604028611', 'date': '19/11/06', 'time': '01:37:40 GMT+1.0', 'charset': 'utf16-be', 'header_iei': 0, 'header_ie_data': '330202',
                         'header_multipart_ref_id': 51, 'header_multipart_nb_of_part': 2, 'header_multipart_current_part_nb': 2,
                         'sms': 'ENDSecond part here °=° !',
                         'sms_encoded': '0045004E0044005300650063006F006E00640020007000610072007400200068006500720065002000B0003D00B000200021'
                       }
                     ])

    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0),[])
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0),[])


  @patch('serial.Serial', new=MockSerial)
  def test_failed_get_sms_7bit_8bit_ucs2(self):
    logging.debug("test_failed_get_sms_7bit_8bit_ucs2")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # PDU not hexa content
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'+CMGL: 1,0,,35\r\n'},
                               {'OUT': b'NOT HEXA *snif*\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0), [])

    # PDU not valid
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'+CMGL: 1,0,,35\r\n'},
                               {'OUT': b'96456465A465A56BA46DFABABABAADAB96456465A465A56BA46DFABABABAADAB\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0), [])

    # Basic error
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               {'OUT': b'ERROR\r\n'}])
    self.assertEqual(gsm.getSMS(waiting_time_sec=0), [])

  @patch('serial.Serial', new=MockSerial)
  def test_all_delete_sms(self):
    logging.debug("test_all_delete_sms")
    gsm = GSMTC35.GSMTC35()
    MockSerial.initializeMock(MockSerial.getDefaultConfigForSetup())
    self.assertTrue(gsm.setup(_port="COM_FAKE"))

    # Delete Normal SMS + Extended in 7 bit and ucs2 SMS
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               # 7 bit normal SMS
                               {'OUT': b'+CMGL: 1,0,,35\r\n'},
                               {'OUT': b'07913396050046F6040B913306048216F100009111601043304012C2F03C3D06DD40E2347D0E9A36A7A010\r\n'},
                               # 7 bit extended SMS
                               {'OUT': b'+CMGL: 3,0,,159\r\n'},
                               {'OUT': b'07913396050036F8440B913306048216F1000091116010631340A00500033202018A787AD94D2E93413790384D074D9B5310AAD99CA640A15028140A815C2E97CBE572B95C2E97CBE572B95C2E90CBE572B95C2E97CBE572B95C2E97CBE572815C2E97CBE572B95C2E97CBE572B95C2E97CBE502B95C2E97CBE572B95C2E97CBE572B95C2097CBE572B95C2E97CBE572B95C2E97CBE572B95C2E97CBE502B95C2E97CBE572B95C\r\n'},
                               {'OUT': b'+CMGL: 4,0,,46\r\n'},
                               {'OUT': b'07913396050036F8440B913306048216F10000911160106323401E0500033202025C2E97ABE8244ECBE3B79B0C8287E57410BA2C2F03\r\n'},
                               # UCS2 normal SMS
                               {'OUT': b'+CMGL: 2,0,,63\r\n'},
                               {'OUT': b'07913396050046F4040B913306048216F10008911160104345402C004200610073006900630020005500430053003200200053004D0053002000210020007C00B0002E00B0007C\r\n'},
                               # UCS2 extended SMS
                               {'OUT': b'+CMGL: 5,0,,159\r\n'},
                               {'OUT': b'07913396050036F6440B913306048216F10008911160107393408C0500033302010045007800740065006E0064006500640020005500430053003200200053004D005300200028004D004D005300290020007C00B0002E00B0007C0020002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E0020002E002E002E002E002E002E002E\r\n'},
                               {'OUT': b'+CMGL: 6,0,,75\r\n'},
                               {'OUT': b'07913396050036F6440B913306048216F1000891116010730440380500033302020045004E0044005300650063006F006E00640020007000610072007400200068006500720065002000B0003D00B000200021\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=3\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=4\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=2\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=5\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=6\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertTrue(gsm.deleteSMS())

    # Error while deleting sms will try to delete others
    MockSerial.initializeMock([{'IN': b'AT+CMGF=0\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGL=4\r\n'},
                               # 7 bit normal SMS
                               {'OUT': b'+CMGL: 1,0,,35\r\n'},
                               {'OUT': b'07913396050046F6040B913306048216F100009111601043304012C2F03C3D06DD40E2347D0E9A36A7A010\r\n'},
                               # 7 bit extended SMS
                               {'OUT': b'+CMGL: 3,0,,159\r\n'},
                               {'OUT': b'07913396050036F8440B913306048216F1000091116010631340A00500033202018A787AD94D2E93413790384D074D9B5310AAD99CA640A15028140A815C2E97CBE572B95C2E97CBE572B95C2E90CBE572B95C2E97CBE572B95C2E97CBE572815C2E97CBE572B95C2E97CBE572B95C2E97CBE502B95C2E97CBE572B95C2E97CBE572B95C2097CBE572B95C2E97CBE572B95C2E97CBE572B95C2E97CBE502B95C2E97CBE572B95C\r\n'},
                               {'OUT': b'+CMGL: 4,0,,46\r\n'},
                               {'OUT': b'07913396050036F8440B913306048216F10000911160106323401E0500033202025C2E97ABE8244ECBE3B79B0C8287E57410BA2C2F03\r\n'},
                               # UCS2 normal SMS
                               {'OUT': b'+CMGL: 2,0,,63\r\n'},
                               {'OUT': b'07913396050046F4040B913306048216F10008911160104345402C004200610073006900630020005500430053003200200053004D0053002000210020007C00B0002E00B0007C\r\n'},
                               # UCS2 extended SMS
                               {'OUT': b'+CMGL: 5,0,,159\r\n'},
                               {'OUT': b'07913396050036F6440B913306048216F10008911160107393408C0500033302010045007800740065006E0064006500640020005500430053003200200053004D005300200028004D004D005300290020007C00B0002E00B0007C0020002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E002E0020002E002E002E002E002E002E002E\r\n'},
                               {'OUT': b'+CMGL: 6,0,,75\r\n'},
                               {'OUT': b'07913396050036F6440B913306048216F1000891116010730440380500033302020045004E0044005300650063006F006E00640020007000610072007400200068006500720065002000B0003D00B000200021\r\n'},
                               {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGF=1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=1\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=3\r\n'}, {'OUT': b'ERROR\r\n'},
                               {'IN': b'AT+CMGD=4\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=2\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=5\r\n'}, {'OUT': b'OK\r\n'},
                               {'IN': b'AT+CMGD=6\r\n'}, {'OUT': b'OK\r\n'}])
    self.assertFalse(gsm.deleteSMS())

if __name__ == '__main__':
  logger = logging.getLogger()
  logger.setLevel(logging.DEBUG)
  unittest.main()
