"""Bounded child-stderr pipe drained to an exclusive parent-only trace file."""
import hashlib,os,pathlib,stat
class Trace:
    def __init__(self,directory,max_bytes=8*1024*1024):
        self.path=pathlib.Path(directory).resolve(strict=True)/'worker_dyld.stderr'
        self.fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        st=os.fstat(self.fd);self.identity=(st.st_dev,st.st_ino);self.max_bytes=max_bytes;self.count=0;self.eof=False
        self.readfd,self.writefd=os.pipe();os.set_blocking(self.readfd,False)
    def bind_child_stderr(self):
        os.dup2(self.writefd,2);os.set_inheritable(2,True)
        os.close(self.writefd);os.close(self.readfd);os.close(self.fd)
    def parent_after_fork(self):os.close(self.writefd);self.writefd=None
    def drain(self):
        while not self.eof:
            try:data=os.read(self.readfd,65536)
            except BlockingIOError:break
            if not data:self.eof=True;break
            if self.count+len(data)>self.max_bytes:raise ValueError('trace byte cap')
            pos=0
            while pos<len(data):pos+=os.write(self.fd,data[pos:])
            self.count+=len(data)
    def snapshot(self):
        self.drain()
        if not self.eof:raise ValueError('trace pipe not closed')
        os.fsync(self.fd);f=os.fstat(self.fd);p=os.lstat(self.path)
        if not stat.S_ISREG(p.st_mode) or (f.st_dev,f.st_ino)!=self.identity or (p.st_dev,p.st_ino)!=self.identity or f.st_nlink!=1:raise ValueError('trace file identity changed')
        h=hashlib.sha256();offset=0
        while True:
            data=os.pread(self.fd,1024*1024,offset)
            if not data:break
            h.update(data);offset+=len(data)
        if offset!=f.st_size or offset!=self.count:raise ValueError('trace changed during read')
        return {'path':str(self.path),'sha256':h.hexdigest(),'bytes':offset,'device':f.st_dev,'inode':f.st_ino}
    def close(self):
        for fd in (self.writefd,self.readfd,self.fd):
            if fd is not None:
                try:os.close(fd)
                except OSError:pass
