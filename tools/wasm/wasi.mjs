// wasi.mjs — the WASI preview 1 calls a Myla program built for wasm32-wasi
// makes (MYLA-158, D125), over Node's synchronous file system API.
//
// A shim of our own instead of `node:wasi`: Node 22's crashes (a
// segmentation fault) when the program's memory grows between two calls,
// and the page the website needs runs in a browser, which has no WASI at
// all. Every call reads the memory afresh (it may have grown), works on
// the descriptors it keeps, and gives WASI's errno.
//
// Descriptor 3 is the directory the program sees as `/` (`preopen`); the
// program resolves its relative paths against `PWD` itself
// (lib/std/platform_wasm.my). A descriptor watched by `poll_oneoff` counts
// as ready at once: Node can't wait for input without blocking, so a read
// blocks the program as a blocking one would.

import fs from "node:fs";
import path from "node:path";

const ERRNO = {
  E2BIG: 1, EACCES: 2, EAGAIN: 6, EBADF: 8, EEXIST: 20, EINTR: 27, EINVAL: 28, EIO: 29, EISDIR: 31,
  ENOENT: 44, ENOSYS: 52, ENOTDIR: 54, ENOTEMPTY: 55, ENOTSUP: 58, EPERM: 63, EPIPE: 64, ENOTCAPABLE: 76,
};

// A Node error's code as WASI's errno.
function errnoOf(e) {
  return ERRNO[e && e.code] ?? ERRNO.EIO;
}

// A WASI file type (3 a directory, 4 a regular file, 7 a symbolic link).
function fileType(st) {
  if (st.isDirectory()) return 3;
  if (st.isFile()) return 4;
  if (st.isSymbolicLink()) return 7;
  if (st.isCharacterDevice()) return 2;
  return 0;
}

export class ProcExit extends Error {
  constructor(code) {
    super(`exit ${code}`);
    this.code = code;
  }
}

export class Wasi {
  constructor({ args = [], env = {}, preopen = "/" } = {}) {
    this.args = args;
    this.env = Object.entries(env).map(([k, v]) => `${k}=${v}`);
    this.fds = new Map([
      [0, { node: 0 }], [1, { node: 1 }], [2, { node: 2 }],
      [3, { dir: true, path: preopen }],
    ]);
    this.next = 4;
    this.memory = null;
    this.enc = new TextEncoder();
    this.dec = new TextDecoder();
  }

  view() { return new DataView(this.memory.buffer); }
  bytes(p, n) { return new Uint8Array(this.memory.buffer, p, n); }
  str(p, n) { return this.dec.decode(this.bytes(p, n)); }

  // The host path of `p` (`len` bytes) under the directory descriptor `fd`.
  resolve(fd, p, len) {
    const d = this.fds.get(fd);
    if (!d || !d.dir) throw Object.assign(new Error("not a directory"), { code: "EBADF" });
    return path.join(d.path, this.str(p, len));
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
    v.setBigUint64(buf, BigInt(st.dev), true);
    v.setBigUint64(buf + 8, BigInt(st.ino), true);
    v.setUint8(buf + 16, fileType(st));
    v.setBigUint64(buf + 24, BigInt(st.nlink), true);
    v.setBigUint64(buf + 32, BigInt(st.size), true);
    v.setBigUint64(buf + 40, BigInt(Math.trunc(st.atimeMs * 1e6)), true);
    v.setBigUint64(buf + 48, BigInt(Math.trunc(st.mtimeMs * 1e6)), true);
    v.setBigUint64(buf + 56, BigInt(Math.trunc(st.ctimeMs * 1e6)), true);
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

  // Each call wrapped: a Node error becomes its errno.
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
          const t = id === 0 ? BigInt(Date.now()) * 1000000n : process.hrtime.bigint();
          this.view().setBigUint64(out, t, true);
          return 0;
        }),
        proc_exit: (code) => { throw new ProcExit(code); },
        fd_write: g(function (fd, iovs, n, nwritten) {
          const d = this.fds.get(fd);
          if (!d || d.dir) return ERRNO.EBADF;
          let total = 0;
          for (const [p, len] of this.iovecs(iovs, n)) {
            let off = 0;
            while (off < len) {
              try {
                off += fs.writeSync(d.node, this.bytes(p + off, len - off));
              } catch (e) {
                if (e.code !== "EAGAIN") throw e;
              }
            }
            total += len;
          }
          this.view().setUint32(nwritten, total, true);
          return 0;
        }),
        fd_read: g(function (fd, iovs, n, nread) {
          const d = this.fds.get(fd);
          if (!d || d.dir) return ERRNO.EBADF;
          let total = 0;
          for (const [p, len] of this.iovecs(iovs, n)) {
            let got;
            for (;;) {
              try {
                got = fs.readSync(d.node, this.bytes(p, len), 0, len, null);
                break;
              } catch (e) {
                if (e.code === "EAGAIN") continue;
                if (e.code === "EOF") { got = 0; break; }
                throw e;
              }
            }
            total += got;
            if (got < len) break;
          }
          this.view().setUint32(nread, total, true);
          return 0;
        }),
        fd_close: g(function (fd) {
          const d = this.fds.get(fd);
          if (!d) return ERRNO.EBADF;
          if (d.node !== undefined && fd > 2) fs.closeSync(d.node);
          this.fds.delete(fd);
          return 0;
        }),
        fd_filestat_get: g(function (fd, buf) {
          const d = this.fds.get(fd);
          if (!d) return ERRNO.EBADF;
          this.writeStat(buf, d.node !== undefined ? fs.fstatSync(d.node) : fs.statSync(d.path));
          return 0;
        }),
        fd_fdstat_get: g(function (fd, buf) {
          const d = this.fds.get(fd);
          if (!d) return ERRNO.EBADF;
          this.bytes(buf, 24).fill(0);
          this.view().setUint8(buf, d.dir ? 3 : 4);
          return 0;
        }),
        fd_readdir: g(function (fd, buf, len, cookie, used) {
          const d = this.fds.get(fd);
          if (!d || !d.dir) return ERRNO.EBADF;
          if (!d.entries) {
            d.entries = [".", ".."].map((name) => ({ name, type: 3 }))
              .concat(fs.readdirSync(d.path, { withFileTypes: true })
                .map((e) => ({ name: e.name, type: e.isDirectory() ? 3 : e.isFile() ? 4 : e.isSymbolicLink() ? 7 : 0 })));
          }
          let at = 0;
          for (let i = Number(cookie); i < d.entries.length; i++) {
            const name = this.enc.encode(d.entries[i].name);
            const rec = new Uint8Array(24 + name.length);
            const v = new DataView(rec.buffer);
            v.setBigUint64(0, BigInt(i + 1), true);
            v.setBigUint64(8, 0n, true);
            v.setUint32(16, name.length, true);
            v.setUint8(20, d.entries[i].type);
            rec.set(name, 24);
            const n = Math.min(rec.length, len - at);
            this.bytes(buf + at, n).set(rec.subarray(0, n));
            at += n;
            if (at === len) break;
          }
          this.view().setUint32(used, at, true);
          return 0;
        }),
        path_open: g(function (dirfd, _dirflags, p, len, oflags, _rights, _inherit, _fdflags, out) {
          const host = this.resolve(dirfd, p, len);
          let entry;
          if (oflags & 2) {
            if (!fs.statSync(host).isDirectory()) return ERRNO.ENOTDIR;
            entry = { dir: true, path: host };
          } else {
            const flags = (oflags & 1) ? ((oflags & 4) ? "wx" : (oflags & 8) ? "w" : "a") : "r";
            if (flags === "r" && fs.statSync(host).isDirectory()) {
              entry = { dir: true, path: host };
            } else {
              entry = { node: fs.openSync(host, flags), path: host };
            }
          }
          const fd = this.next++;
          this.fds.set(fd, entry);
          this.view().setUint32(out, fd, true);
          return 0;
        }),
        path_filestat_get: g(function (dirfd, flags, p, len, buf) {
          const host = this.resolve(dirfd, p, len);
          this.writeStat(buf, (flags & 1) ? fs.statSync(host) : fs.lstatSync(host));
          return 0;
        }),
        path_create_directory: g(function (dirfd, p, len) { fs.mkdirSync(this.resolve(dirfd, p, len)); return 0; }),
        path_remove_directory: g(function (dirfd, p, len) { fs.rmdirSync(this.resolve(dirfd, p, len)); return 0; }),
        path_unlink_file: g(function (dirfd, p, len) { fs.unlinkSync(this.resolve(dirfd, p, len)); return 0; }),
        path_rename: g(function (fd1, p1, l1, fd2, p2, l2) {
          fs.renameSync(this.resolve(fd1, p1, l1), this.resolve(fd2, p2, l2));
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
            if (ms > 0) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
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
