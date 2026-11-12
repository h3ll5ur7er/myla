// node_fs.mjs — the host's file system and standard streams for wasi.mjs,
// through Node's synchronous API (MYLA-158).

import fs from "node:fs";
import { fsError, seekTo } from "./wasi.mjs";

function typeOf(st) {
  if (st.isDirectory()) return 3;
  if (st.isFile()) return 4;
  if (st.isSymbolicLink()) return 7;
  if (st.isCharacterDevice()) return 2;
  return 0;
}

function statOf(st) {
  return { type: typeOf(st), size: st.size, ino: st.ino, nlink: st.nlink, mtimeNs: Math.trunc(st.mtimeMs * 1e6) };
}

export class NodeFs {
  // Created without truncating: written from the start, as O_CREAT alone
  // does ("a" would append every write wherever the position is, MYLA-298).
  // With the access asked for (MYLA-336), `read` and `write` give it, and
  // `append` writes at the end. A handle keeps its own cursor (Node has no
  // lseek): a regular file is read and written at it, anything else where
  // the system's cursor is, and can't seek (ESPIPE).
  open(path, { create, trunc, excl, read, write, append }) {
    const c = fs.constants;
    let flags = !create ? "r" : excl ? "wx" : trunc ? "w" : c.O_WRONLY | c.O_CREAT;
    if (read !== undefined) {
      flags = (read && write ? c.O_RDWR : write ? c.O_WRONLY : c.O_RDONLY) |
        (create ? c.O_CREAT : 0) | (trunc ? c.O_TRUNC : 0) | (excl ? c.O_EXCL : 0) | (append ? c.O_APPEND : 0);
    }
    const fd = fs.openSync(path, flags);
    return { fd, pos: 0, seekable: fs.fstatSync(fd).isFile(), append: !!append };
  }
  read(h, u8) {
    const n = fs.readSync(h.fd, u8, 0, u8.length, h.seekable ? h.pos : null);
    if (h.seekable) h.pos += n;
    return n;
  }
  write(h, u8) {
    const n = fs.writeSync(h.fd, u8, 0, u8.length, h.seekable ? h.pos : null);
    // an appending write went to the end, whatever the cursor said
    if (h.seekable) h.pos = h.append ? fs.fstatSync(h.fd).size : h.pos + n;
    return n;
  }
  seek(h, offset, whence) {
    if (!h.seekable) throw fsError("ESPIPE");
    h.pos = seekTo(whence === 0 ? 0 : whence === 1 ? h.pos : fs.fstatSync(h.fd).size, offset);
    return h.pos;
  }
  close(h) { fs.closeSync(h.fd); }
  fstat(h) { return statOf(fs.fstatSync(h.fd)); }
  stat(path, follow) { return statOf(follow ? fs.statSync(path) : fs.lstatSync(path)); }
  readdir(path) {
    return fs.readdirSync(path, { withFileTypes: true })
      .map((e) => ({ name: e.name, type: e.isDirectory() ? 3 : e.isFile() ? 4 : e.isSymbolicLink() ? 7 : 0 }));
  }
  mkdir(path) { fs.mkdirSync(path); }
  rmdir(path) { fs.rmdirSync(path); }
  unlink(path) { fs.unlinkSync(path); }
  rename(a, b) { fs.renameSync(a, b); }
}

// A write of all of `u8` to the descriptor `fd`, again after EAGAIN (a
// non-blocking pipe that is full) a millisecond later: Node has no
// synchronous poll, and trying again at once spun (MYLA-457: 0.68 s of CPU
// over 0.72 s for 2 MiB to a slow reader).
function writeAll(fd, u8) {
  let off = 0;
  while (off < u8.length) {
    try {
      off += fs.writeSync(fd, u8, off, u8.length - off);
    } catch (e) {
      if (e.code !== "EAGAIN") throw e;
      pause(1);
    }
  }
}

// The thread asleep for `ms` milliseconds.
function pause(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

// The process's own standard streams.
export const nodeStdio = {
  stdin(u8) {
    for (;;) {
      try {
        return fs.readSync(0, u8, 0, u8.length, null);
      } catch (e) {
        if (e.code === "EAGAIN") continue;
        if (e.code === "EOF") return 0;
        throw e;
      }
    }
  },
  stdout(u8) { writeAll(1, u8); },
  stderr(u8) { writeAll(2, u8); },
};
