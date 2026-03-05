import { defineConfig } from "vite";
import { peerDependencies } from "./package.json";


export default defineConfig({
    build: {
        lib: {
            entry: "./src/index.ts",
            name: "buckaroo-js-core",
            fileName: () => `index.esm.js`,
            formats: ["es"],
        },
        rollupOptions: {
            external: ["react", "react-dom", 'react/jsx-runtime'],
        },
        sourcemap: false,
        emptyOutDir: true,
        minify: true
    },
    plugins: [],
    test: {
        globals: true,
        environment: "happy-dom",
        setupFiles: "./setupTests.ts",
        css: false,
        include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    },
});
