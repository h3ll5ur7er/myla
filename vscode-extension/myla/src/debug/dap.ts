// The Debug Adapter Protocol's base protocol: JSON messages framed by a
// Content-Length header, as VS Code speaks it over stdio
// (https://microsoft.github.io/debug-adapter-protocol/overview#base-protocol).

const SEPARATOR = Buffer.from("\r\n\r\n", "latin1");

/** One message, framed. */
export function encodeMessage(message: unknown): Buffer {
  const body = Buffer.from(JSON.stringify(message), "utf8");
  return Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, "latin1"), body]);
}

/** Collects bytes and hands each complete message to `onMessage`. */
export class MessageReader {
  private buffer: Buffer = Buffer.alloc(0);
  private readonly onMessage: (message: unknown) => void;
  private readonly onError: (error: Error) => void;

  constructor(onMessage: (message: unknown) => void, onError: (error: Error) => void = () => {}) {
    this.onMessage = onMessage;
    this.onError = onError;
  }

  push(chunk: Buffer): void {
    this.buffer = this.buffer.length ? Buffer.concat([this.buffer, chunk]) : chunk;
    for (;;) {
      const end = this.buffer.indexOf(SEPARATOR);
      if (end < 0) return;
      const header = this.buffer.subarray(0, end).toString("latin1");
      const match = /^content-length:\s*(\d+)\s*$/im.exec(header);
      if (!match) {
        this.onError(new Error(`a message header without Content-Length: ${JSON.stringify(header)}`));
        this.buffer = this.buffer.subarray(end + SEPARATOR.length);
        continue;
      }
      const length = Number(match[1]);
      const start = end + SEPARATOR.length;
      if (this.buffer.length < start + length) return;
      const body = this.buffer.subarray(start, start + length).toString("utf8");
      this.buffer = this.buffer.subarray(start + length);
      let message: unknown;
      try {
        message = JSON.parse(body);
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)));
        continue;
      }
      this.onMessage(message);
    }
  }
}
