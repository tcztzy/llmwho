import { dirname } from "node:path";
import { fileURLToPath } from "node:url";


export const moduleDirectory = dirname(fileURLToPath(import.meta.url));
