// node_fs.mjs — the host's file system and standard streams for wasi.mjs,
// through Node's synchronous API (MYLA-158).

import fs from "node:fs";

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
  open(path, { create, trunc, excl }) {
    const c = fs.constants;
    const flags = !create ? "r" : excl ? "wx" : trunc ? "w" : c.O_WRONLY | c.O_CREAT;
    return fs.openSync(path, flags);
  }
  read(h, u8) { return fs.readSync(h, u8, 0, u8.length, null); }
  write(h, u8) { return fs.writeSync(h, u8); }
  close(h) { fs.closeSync(h); }
  fstat(h) { return statOf(fs.fstatSync(h)); }
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

// A write of all of `u8` to the descriptor `fd`, again after EAGAIN.
function writeAll(fd, u8) {
  let off = 0;
  while (off < u8.length) {
    try {
      off += fs.writeSync(fd, u8, off, u8.length - off);
    } catch (e) {
      if (e.code !== "EAGAIN") throw e;
    }
  }
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
