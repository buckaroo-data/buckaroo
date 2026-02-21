import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const INPUT = process.env.INPUT;
if (!INPUT) {
  throw new Error("INPUT environment variable is not set");
}

export default defineConfig({
  plugins: [viteSingleFile()],
  build: {
    rollupOptions: { input: INPUT },
    outDir: "dist",
    emptyOutDir: false,
  },
});
