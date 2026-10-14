import { File } from "node:buffer";
import fs from "node:fs/promises";
import { fal } from "@fal-ai/client";

async function readInput() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function configure() {
  if (!process.env.FAL_KEY) throw new Error("Set FAL_KEY in this project's .env file.");
  fal.config({ credentials: process.env.FAL_KEY });
}

async function upload(paths) {
  return Promise.all(paths.map(async (filePath) => {
    const bytes = await fs.readFile(filePath);
    const name = filePath.split(/[\\/]/).pop();
    return fal.storage.upload(new File([bytes], name, { type: "application/octet-stream" }));
  }));
}

try {
  configure();
  const action = process.argv[2];
  const input = await readInput();
  let result;
  if (action === "upload") result = { urls: await upload(input.paths) };
  else if (action === "submit") {
    const queued = await fal.queue.submit(input.model, { input: input.input });
    result = { request_id: queued.request_id, model: input.model };
  } else if (action === "status") {
    result = await fal.queue.status(input.model, { requestId: input.request_id, logs: true });
  } else if (action === "result") {
    result = await fal.queue.result(input.model, { requestId: input.request_id });
  } else throw new Error(`Unknown Fal bridge action: ${action}`);
  process.stdout.write(JSON.stringify(result));
} catch (error) {
  process.stderr.write(error?.message || String(error));
  process.exitCode = 1;
}
