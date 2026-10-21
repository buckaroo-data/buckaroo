/// <reference types="vitest" />
//import { defineConfig } from 'vitest/config'
import { defineConfig } from "vite";
import dts from "vite-plugin-dts";
import { peerDependencies } from "./package.json";


export default defineConfig({
    build: {
        lib: {
            entry: "./src/index.ts", // Specifies the entry point for building the library.
            name: "vite-react-ts-button", // Sets the name of the generated library.
            fileName: (format) => `index.${format}.js`, // Generates the output file name based on the format.
            formats: ["cjs", "es", "esm"], // Specifies the output formats (CommonJS and ES modules).
        },
        rollupOptions: {
            external: ["react", "react-dom", 'react/jsx-runtime'],
        },
        sourcemap: true, // Generates source maps for debugging.
        emptyOutDir: true, // Clears the output directory before building.
        minify: true
    },

    transform: {
	"^.+\\.tsx?$": "ts-jest",
    },
    plugins: [
        // Generates TypeScript declaration files (d.ts). package.json is in tsconfig's include so src/version.ts can
        // import it under `composite`; it gets no declaration of its own.
        dts({ beforeWriteFile: (filePath) => (filePath.endsWith("package.json.d.ts") ? false : undefined) }),
    ],
    test: {
        globals: true,
        environment: "jsdom",
        setupFiles: "./setupTests.ts",
    },
});
