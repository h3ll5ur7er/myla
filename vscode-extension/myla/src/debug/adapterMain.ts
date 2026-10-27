// The Myla debug adapter as a program speaking DAP on stdin/stdout:
// `node out/debugAdapter.js`. VS Code runs the adapter in-process instead;
// this entry point serves other DAP clients and the integration test.
import { encodeMessage, MessageReader } from "./dap.ts";
import { MylaDebugSession } from "./session.ts";
import type { DebugProtocol } from "@vscode/debugprotocol";

const session = new MylaDebugSession((message) => {
  process.stdout.write(encodeMessage(message));
  if (message.type === "response" && (message as DebugProtocol.Response).command === "disconnect") {
    session.dispose();
    process.exit(0);
  }
});
const reader = new MessageReader(
  (message) => session.handleMessage(message as DebugProtocol.ProtocolMessage),
  (error) => process.stderr.write(`myla debug adapter: ${error.message}\n`),
);
process.stdin.on("data", (chunk: Buffer) => reader.push(chunk));
process.stdin.on("end", () => {
  session.dispose();
  process.exit(0);
});
