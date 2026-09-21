import os
from pathlib import Path
import unittest
from unittest.mock import patch
import server_control as control


class ServerIdentityTests(unittest.TestCase):
    def test_current_process_start_stamp(self):
        self.assertIsNotNone(control.process_stamp(os.getpid()))

    def test_pid_reuse_never_signalled(self):
        state=dict(pid=os.getpid(),start_ticks='incorrect',token='test')
        with patch.object(control.os,'killpg') as kill:
            control.terminate(state)
            kill.assert_not_called()

    def test_unrelated_process_never_signalled(self):
        state=dict(pid=os.getpid(),start_ticks=control.process_stamp(os.getpid()),token='not-our-server')
        with patch.object(control.os,'killpg') as kill:
            control.terminate(state)
            kill.assert_not_called()

    def test_dead_process_is_not_owned(self):
        self.assertFalse(control.owned(dict(pid=99999999,start_ticks='1',token='test')))


if __name__=='__main__':unittest.main()
