import os,pathlib,tempfile,unittest
import trace33
class TraceTest(unittest.TestCase):
    def test_exclusive_pipe_and_file_replacement_refused(self):
        with tempfile.TemporaryDirectory() as t:
            x=trace33.Trace(t)
            try:
                os.write(x.writefd,b'test');x.parent_after_fork();x.drain();self.assertEqual(x.snapshot()['bytes'],4)
                with self.assertRaises(FileExistsError):trace33.Trace(t)
                os.unlink(x.path);pathlib.Path(x.path).write_bytes(b'forged')
                with self.assertRaisesRegex(ValueError,'identity'):x.snapshot()
            finally:x.close()
    def test_child_cannot_seek_or_truncate_pipe(self):
        with tempfile.TemporaryDirectory() as t:
            x=trace33.Trace(t);pid=os.fork()
            if pid==0:
                try:
                    x.bind_child_stderr()
                    for fn in (lambda:os.lseek(2,0,os.SEEK_SET),lambda:os.ftruncate(2,0)):
                        try:fn();os._exit(3)
                        except OSError:pass
                    os.write(2,b'pipe');os._exit(0)
                except BaseException:os._exit(4)
            try:
                x.parent_after_fork();_,status=os.waitpid(pid,0)
                self.assertEqual(status,0);self.assertEqual(x.snapshot()['bytes'],4)
            finally:x.close()
    def test_bounded_and_requires_eof(self):
        with tempfile.TemporaryDirectory() as t:
            x=trace33.Trace(t,max_bytes=2)
            try:
                with self.assertRaisesRegex(ValueError,'not closed'):x.snapshot()
                os.write(x.writefd,b'abc');x.parent_after_fork()
                with self.assertRaisesRegex(ValueError,'byte cap'):x.drain()
            finally:x.close()
if __name__=='__main__':unittest.main()
