// mem_fs.mjs — files in memory for wasi.mjs (MYLA-158): what a page gives a
// Myla program built for wasm. Paths are absolute (`/main.my`); a
// directory exists when it was made or a file lies under it.

import { fsError, joinPath } from "./wasi.mjs";

export class MemFs {
  // `files`: path (relative to `/` or absolute) to text or bytes.
  constructor(files = {}) {
    this.files = new Map();
    this.dirs = new Set(["/"]);
    this.ino = 1;
    const enc = new TextEncoder();
    for (const [p, data] of Object.entries(files)) {
      const path = joinPath("/", p);
      this.files.set(path, { data: typeof data === "string" ? enc.encode(data) : new Uint8Array(data), ino: this.ino++ });
      this.addParents(path);
    }
  }

  addParents(path) {
    let p = path;
    while ((p = p.slice(0, p.lastIndexOf("/")) || "/") !== "/") this.dirs.add(p);
  }

  parentExists(path) {
    const parent = path.slice(0, path.lastIndexOf("/")) || "/";
    return this.dirs.has(parent);
  }

  // The file's bytes as text (what a program wrote), or undefined.
  text(path) {
    const f = this.files.get(joinPath("/", path));
    return f && new TextDecoder().decode(f.data);
  }

  open(path, { create, trunc, excl, read, write, append }) {
    let f = this.files.get(path);
    if (this.dirs.has(path)) throw fsError("EISDIR");
    if (f && excl) throw fsError("EEXIST");
    if (!f) {
      if (!create) throw fsError("ENOENT");
      if (!this.parentExists(path)) throw fsError("ENOENT");
      f = { data: new Uint8Array(0), ino: this.ino++ };
      this.files.set(path, f);
    } else if (trunc) {
      f.data = new Uint8Array(0);
    }
    // the access asked for (MYLA-336): from the start, the end for appending
    if (read !== undefined) return { file: f, pos: 0, read, write, append: !!append };
    return { file: f, pos: create && !trunc ? f.data.length : 0, read: true, write: true, append: false };
  }

  read(h, u8) {
    if (!h.read) throw fsError("EBADF");
    const n = Math.max(0, Math.min(u8.length, h.file.data.length - h.pos));
    u8.set(h.file.data.subarray(h.pos, h.pos + n));
    h.pos += n;
    return n;
  }

  write(h, u8) {
    if (!h.write) throw fsError("EBADF");
    if (h.append) h.pos = h.file.data.length;
    const end = h.pos + u8.length;
    if (end > h.file.data.length) {
      const grown = new Uint8Array(end);
      grown.set(h.file.data);
      h.file.data = grown;
    }
    h.file.data.set(u8, h.pos);
    h.pos = end;
    return u8.length;
  }

  seek(h, offset, whence) {
    const at = (whence === 0 ? 0 : whence === 1 ? h.pos : h.file.data.length) + offset;
    if (at < 0) throw fsError("EINVAL");
    h.pos = at;
    return at;
  }

  close() {}

  fstat(h) {
    return { type: 4, size: h.file.data.length, ino: h.file.ino };
  }

  stat(path) {
    if (this.dirs.has(path)) return { type: 3, size: 0 };
    const f = this.files.get(path);
    if (!f) throw fsError("ENOENT");
    return { type: 4, size: f.data.length, ino: f.ino };
  }

  readdir(path) {
    if (!this.dirs.has(path)) throw fsError(this.files.has(path) ? "ENOTDIR" : "ENOENT");
    const prefix = path === "/" ? "/" : path + "/";
    const out = [];
    for (const d of this.dirs) {
      if (d !== path && d.startsWith(prefix) && !d.slice(prefix.length).includes("/")) out.push({ name: d.slice(prefix.length), type: 3 });
    }
    for (const f of this.files.keys()) {
      if (f.startsWith(prefix) && !f.slice(prefix.length).includes("/")) out.push({ name: f.slice(prefix.length), type: 4 });
    }
    return out.sort((a, b) => (a.name < b.name ? -1 : 1));
  }

  mkdir(path) {
    if (this.dirs.has(path) || this.files.has(path)) throw fsError("EEXIST");
    if (!this.parentExists(path)) throw fsError("ENOENT");
    this.dirs.add(path);
  }

  rmdir(path) {
    if (!this.dirs.has(path)) throw fsError(this.files.has(path) ? "ENOTDIR" : "ENOENT");
    if (this.readdir(path).length > 0) throw fsError("ENOTEMPTY");
    this.dirs.delete(path);
  }

  unlink(path) {
    if (this.dirs.has(path)) throw fsError("EISDIR");
    if (!this.files.delete(path)) throw fsError("ENOENT");
  }

  rename(a, b) {
    const f = this.files.get(a);
    if (!f) throw fsError("ENOENT");
    if (!this.parentExists(b)) throw fsError("ENOENT");
    this.files.delete(a);
    this.files.set(b, f);
  }
}
