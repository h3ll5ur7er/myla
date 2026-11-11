// wasi.mjs — the WASI preview 1 calls a Myla program built for wasm32-wasi
// makes (MYLA-158, D125), over a file system and standard streams given to
// it: the host's (node_fs.mjs) or files in memory (mem_fs.mjs, for a page).
// It imports nothing of Node's, so a browser runs it too.
//
// A shim of our own instead of `node:wasi`: Node 22's crashes (a
// segmentation fault) when the program's memory grows between two calls,
// and a browser has no WASI at all. Every call reads the memory afresh (it
// may have grown) and gives WASI's errno.
//
// Descriptor 3 is the directory the program sees as `/`; the program
// resolves its relative paths against `PWD` itself
// (lib/std/platform_wasm.my). A descriptor watched by `poll_oneoff` counts
// as ready at once (a host can't wait for input without blocking), so a
// read blocks the program as a blocking one would.
//
// A file system gives: `open(path, {create, trunc, excl, dir, read, write,
// append})` a handle (`read` and `write` the access asked for, undefined
// when the program asked for every right, as its own reads and writes of
// whole files do; MYLA-336), `read(handle, bytes)` and `write(handle,
// bytes)` how many at the handle's cursor, `seek(handle, offset, whence)`
// the new cursor (whence 0 the start, 1 the cursor, 2 the end; `offset` a
// BigInt, `seekTo` the bounds; the cursor unmoved on a failure), `close`,
// `fstat(handle)` and `stat(path, follow)` `{type, size, ino, nlink,
// mtimeNs}` (type 3 a directory, 4 a regular file, 7 a symbolic link),
// `readdir(path)` `[{name, type}]`, `mkdir`, `rmdir`, `unlink`,
// `rename(from, to)`; a failure throws an error whose `code` is an errno's
// name (`ENOENT`, …). The streams: `stdin(bytes)` how many it read (0 at the
// end), `stdout(bytes)`, `stderr(bytes)`.

// WASI preview 1's errnos, every one (MYLA-426: ELOOP, ENAMETOOLONG and
// the others were EIO before).
export const ERRNO = {
  E2BIG: 1, EACCES: 2, EADDRINUSE: 3, EADDRNOTAVAIL: 4, EAFNOSUPPORT: 5, EAGAIN: 6, EALREADY: 7, EBADF: 8, EBADMSG: 9,
  EBUSY: 10, ECANCELED: 11, ECHILD: 12, ECONNABORTED: 13, ECONNREFUSED: 14, ECONNRESET: 15, EDEADLK: 16, EDESTADDRREQ: 17,
  EDOM: 18, EDQUOT: 19, EEXIST: 20, EFAULT: 21, EFBIG: 22, EHOSTUNREACH: 23, EIDRM: 24, EILSEQ: 25, EINPROGRESS: 26,
  EINTR: 27, EINVAL: 28, EIO: 29, EISCONN: 30, EISDIR: 31, ELOOP: 32, EMFILE: 33, EMLINK: 34, EMSGSIZE: 35, EMULTIHOP: 36,
  ENAMETOOLONG: 37, ENETDOWN: 38, ENETRESET: 39, ENETUNREACH: 40, ENFILE: 41, ENOBUFS: 42, ENODEV: 43, ENOENT: 44,
  ENOEXEC: 45, ENOLCK: 46, ENOLINK: 47, ENOMEM: 48, ENOMSG: 49, ENOPROTOOPT: 50, ENOSPC: 51, ENOSYS: 52, ENOTCONN: 53,
  ENOTDIR: 54, ENOTEMPTY: 55, ENOTRECOVERABLE: 56, ENOTSOCK: 57, ENOTSUP: 58, ENOTTY: 59, ENXIO: 60, EOVERFLOW: 61,
  EOWNERDEAD: 62, EPERM: 63, EPIPE: 64, EPROTO: 65, EPROTONOSUPPORT: 66, EPROTOTYPE: 67, ERANGE: 68, EROFS: 69,
  ESPIPE: 70, ESRCH: 71, ESTALE: 72, ETIMEDOUT: 73, ETXTBSY: 74, EXDEV: 75, ENOTCAPABLE: 76,
};
// Node's names for two of them
ERRNO.EWOULDBLOCK = ERRNO.EAGAIN;
ERRNO.EOPNOTSUPP = ERRNO.ENOTSUP;

// An error's code as WASI's errno.
function errnoOf(e) {
  return ERRNO[e && e.code] ?? ERRNO.EIO;
}

// The cursor `offset` from `base` (both may be BigInts): a number from 0 to
// 2^53 - 1, the largest offset a JavaScript number holds exactly, as a file
// system with that largest file size gives (EINVAL past it, as Linux's
// lseek does past its own; MYLA-426).
export function seekTo(base, offset) {
  const at = BigInt(base) + BigInt(offset);
  if (at < 0n || at > BigInt(Number.MAX_SAFE_INTEGER)) throw fsError("EINVAL");
  return Number(at);
}

// An error with the errno name `code` (what a file system throws).
export function fsError(code) {
  return Object.assign(new Error(code), { code });
}

// `a` joined with the relative `b`, `.` and `..` resolved.
export function joinPath(a, b) {
  const parts = [];
  for (const p of (b.startsWith("/") ? b : `${a}/${b}`).split("/")) {
    if (p === "" || p === ".") continue;
    if (p === "..") parts.pop();
    else parts.push(p);
  }
  return "/" + parts.join("/");
}

export class ProcExit extends Error {
  constructor(code) {
    super(`exit ${code}`);
    this.code = code;
  }
}

// The monotonic clock in nanoseconds.
function monotonicNs() {
  return BigInt(Math.round(globalThis.performance.now() * 1e6));
}

// The thread asleep for `ms` milliseconds (a busy wait where it may not
// block, as on a page's main thread).
function sleepMs(ms) {
  try {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
  } catch {
    const end = globalThis.performance.now() + ms;
    while (globalThis.performance.now() < end) { /* waiting */ }
  }
}

export class Wasi {
  constructor({ args = [], env = {}, fs, stdin, stdout, stderr, root = "/" }) {
    this.args = args;
    this.env = Object.entries(env).map(([k, v]) => `${k}=${v}`);
    this.fs = fs;
    this.stdio = [stdin, stdout, stderr];
    this.fds = new Map([[0, { std: 0 }], [1, { std: 1 }], [2, { std: 2 }], [3, { dir: true, path: root }]]);
    this.next = 4;
    this.memory = null;
    this.enc = new TextEncoder();
    this.dec = new TextDecoder();
  }

  view() { return new DataView(this.memory.buffer); }
  bytes(p, n) { return new Uint8Array(this.memory.buffer, p, n); }
  str(p, n) { return this.dec.decode(this.bytes(p, n).slice()); }

  // The path of `p` (`len` bytes) under the directory descriptor `fd`.
  resolve(fd, p, len) {
    const d = this.fds.get(fd);
    if (!d || !d.dir) throw fsError("EBADF");
    return joinPath(d.path, this.str(p, len));
  }

  // Each iovec of `iovs` (`n` of them): its address and length.
  *iovecs(iovs, n) {
    for (let i = 0; i < n; i++) {
      const v = this.view();
      yield [v.getUint32(iovs + 8 * i, true), v.getUint32(iovs + 8 * i + 4, true)];
    }
  }

  writeStat(buf, st) {
    const v = this.view();
    v.setBigUint64(buf, 0n, true);
    v.setBigUint64(buf + 8, BigInt(st.ino ?? 0), true);
    v.setUint8(buf + 16, st.type);
    v.setBigUint64(buf + 24, BigInt(st.nlink ?? 1), true);
    v.setBigUint64(buf + 32, BigInt(st.size ?? 0), true);
    const t = BigInt(st.mtimeNs ?? 0);
    v.setBigUint64(buf + 40, t, true);
    v.setBigUint64(buf + 48, t, true);
    v.setBigUint64(buf + 56, t, true);
  }

  // A vector of NUL-terminated strings (`args_get`, `environ_get`).
  vector(list, ptrs, buf) {
    let at = buf;
    list.forEach((s, i) => {
      const b = this.enc.encode(s);
      this.view().setUint32(ptrs + 4 * i, at, true);
      this.bytes(at, b.length + 1).set([...b, 0]);
      at += b.length + 1;
    });
    return 0;
  }

  sizes(list, countp, sizep) {
    this.view().setUint32(countp, list.length, true);
    this.view().setUint32(sizep, list.reduce((n, s) => n + this.enc.encode(s).length + 1, 0), true);
    return 0;
  }

  // One read or write of the descriptor `fd` (a stream or an open file).
  io(fd, write, u8) {
    const d = this.fds.get(fd);
    if (!d || d.dir) throw fsError("EBADF");
    if (d.std !== undefined) {
      const s = this.stdio[d.std];
      if (write) { s(u8); return u8.length; }
      return s(u8);
    }
    return write ? this.fs.write(d.handle, u8) : this.fs.read(d.handle, u8);
  }

  // Each call wrapped: a file system's error becomes its errno.
  guard(f) {
    return (...a) => {
      try {
        return f(...a);
      } catch (e) {
        if (e instanceof ProcExit) throw e;
        return errnoOf(e);
      }
    };
  }

  imports() {
    const g = (f) => this.guard(f.bind(this));
    return {
      wasi_snapshot_preview1: {
        args_sizes_get: g(function (c, s) { return this.sizes(this.args, c, s); }),
        args_get: g(function (p, b) { return this.vector(this.args, p, b); }),
        environ_sizes_get: g(function (c, s) { return this.sizes(this.env, c, s); }),
        environ_get: g(function (p, b) { return this.vector(this.env, p, b); }),
        clock_time_get: g(function (id, _precision, out) {
          const t = id === 0 ? BigInt(Date.now()) * 1000000n : monotonicNs();
          this.view().setBigUint64(out, t, true);
          return 0;
        }),
        proc_exit: (code) => { throw new ProcExit(code); },
        fd_write: g(function (fd, iovs, n, nwritten) {
          let total = 0;
          for (const [p, len] of this.iovecs(iovs, n)) {
            let off = 0;
            while (off < len) off += this.io(fd, true, this.bytes(p + off, len - off).slice());
            total += len;
          }
          this.view().setUint32(nwritten, total, true);
          return 0;
        }),
        fd_read: g(function (fd, iovs, n, nread) {
          let total = 0;
          for (const [p, len] of this.iovecs(iovs, n)) {
            const tmp = new Uint8Array(len);
            const got = this.io(fd, false, tmp);
            this.bytes(p, got).set(tmp.subarray(0, got));
            total += got;
            if (got < len) break;
          }
          this.view().setUint32(nread, total, true);
          return 0;
        }),
        fd_close: g(function (fd) {
          const d = this.fds.get(fd);
          if (!d) return ERRNO.EBADF;
          if (d.handle !== undefined) this.fs.close(d.handle);
          this.fds.delete(fd);
          return 0;
        }),
        fd_seek: g(function (fd, offset, whence, out) {
          const d = this.fds.get(fd);
          if (!d) return ERRNO.EBADF;
          if (d.handle === undefined) return d.dir ? ERRNO.EBADF : ERRNO.ESPIPE;
          if (whence > 2) return ERRNO.EINVAL;
          this.view().setBigUint64(out, BigInt(this.fs.seek(d.handle, offset, whence)), true);
          return 0;
        }),
        random_get: g(function (buf, len) {
          // in pieces of 64 KB, the most getRandomValues fills at once
          for (let at = 0; at < len; at += 65536) {
            globalThis.crypto.getRandomValues(this.bytes(buf + at, Math.min(65536, len - at)));
          }
          return 0;
        }),
        fd_filestat_get: g(function (fd, buf) {
          const d = this.fds.get(fd);
          if (!d) return ERRNO.EBADF;
          if (d.std !== undefined) this.writeStat(buf, { type: 2 });
          else this.writeStat(buf, d.handle !== undefined ? this.fs.fstat(d.handle) : this.fs.stat(d.path, true));
          return 0;
        }),
        fd_fdstat_get: g(function (fd, buf) {
          const d = this.fds.get(fd);
          if (!d) return ERRNO.EBADF;
          this.bytes(buf, 24).fill(0);
          this.view().setUint8(buf, d.dir ? 3 : d.std !== undefined ? 2 : 4);
          return 0;
        }),
        fd_readdir: g(function (fd, buf, len, cookie, used) {
          const d = this.fds.get(fd);
          if (!d || !d.dir) return ERRNO.EBADF;
          if (!d.entries) d.entries = [{ name: ".", type: 3 }, { name: "..", type: 3 }, ...this.fs.readdir(d.path)];
          let at = 0;
          for (let i = Number(cookie); i < d.entries.length && at < len; i++) {
            const name = this.enc.encode(d.entries[i].name);
            const rec = new Uint8Array(24 + name.length);
            const v = new DataView(rec.buffer);
            v.setBigUint64(0, BigInt(i + 1), true);
            v.setUint32(16, name.length, true);
            v.setUint8(20, d.entries[i].type);
            rec.set(name, 24);
            const n = Math.min(rec.length, len - at);
            this.bytes(buf + at, n).set(rec.subarray(0, n));
            at += n;
          }
          this.view().setUint32(used, at, true);
          return 0;
        }),
        path_open: g(function (dirfd, _dirflags, p, len, oflags, rights, _inherit, fdflags, out) {
          const path = this.resolve(dirfd, p, len);
          const want = { create: !!(oflags & 1), dir: !!(oflags & 2), excl: !!(oflags & 4), trunc: !!(oflags & 8) };
          // the rights to read (bit 1) and write (bit 6) asked for, unless
          // all were
          if (rights !== -1n) {
            want.read = (rights & 2n) !== 0n;
            want.write = (rights & 64n) !== 0n;
            want.append = !!(fdflags & 1);
          }
          let entry;
          if (!want.create && this.fs.stat(path, true).type === 3) {
            if (want.write) return ERRNO.EISDIR;
            entry = { dir: true, path };
          } else if (want.dir) {
            return ERRNO.ENOTDIR;
          } else {
            entry = { handle: this.fs.open(path, want), path };
          }
          const fd = this.next++;
          this.fds.set(fd, entry);
          this.view().setUint32(out, fd, true);
          return 0;
        }),
        path_filestat_get: g(function (dirfd, flags, p, len, buf) {
          this.writeStat(buf, this.fs.stat(this.resolve(dirfd, p, len), !!(flags & 1)));
          return 0;
        }),
        path_create_directory: g(function (dirfd, p, len) { this.fs.mkdir(this.resolve(dirfd, p, len)); return 0; }),
        path_remove_directory: g(function (dirfd, p, len) { this.fs.rmdir(this.resolve(dirfd, p, len)); return 0; }),
        path_unlink_file: g(function (dirfd, p, len) { this.fs.unlink(this.resolve(dirfd, p, len)); return 0; }),
        path_rename: g(function (fd1, p1, l1, fd2, p2, l2) {
          this.fs.rename(this.resolve(fd1, p1, l1), this.resolve(fd2, p2, l2));
          return 0;
        }),
        poll_oneoff: g(function (subs, events, n, count) {
          // descriptors: ready at once; else the nearest clock, slept for
          const ready = [];
          let nearest = null;
          for (let i = 0; i < n; i++) {
            const s = subs + 48 * i;
            const v = this.view();
            const user = v.getBigUint64(s, true);
            const tag = v.getUint8(s + 8);
            if (tag === 0) {
              const ns = v.getBigUint64(s + 24, true);
              if (nearest === null || ns < nearest.ns) nearest = { user, ns };
            } else {
              ready.push({ user, type: tag });
            }
          }
          if (ready.length === 0 && nearest !== null) {
            const ms = Number(nearest.ns / 1000000n);
            if (ms > 0) sleepMs(ms);
            ready.push({ user: nearest.user, type: 0 });
          }
          ready.forEach((r, i) => {
            const e = events + 32 * i;
            const v = this.view();
            v.setBigUint64(e, r.user, true);
            v.setUint16(e + 8, 0, true);
            v.setUint8(e + 10, r.type);
            v.setBigUint64(e + 16, 1n, true);
            v.setUint16(e + 24, 0, true);
          });
          this.view().setUint32(count, ready.length, true);
          return 0;
        }),
        sched_yield: () => 0,
      },
    };
  }

  // The module's `_start` run: its exit code.
  start(instance) {
    this.memory = instance.exports.memory;
    try {
      instance.exports._start();
      return 0;
    } catch (e) {
      if (e instanceof ProcExit) return e.code;
      throw e;
    }
  }
}
