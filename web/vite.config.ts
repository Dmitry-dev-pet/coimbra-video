import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  build: {
    target: "es2022",
    sourcemap: true,
    rollupOptions: {
      input: {
        main: "index.html",
        parity: "037/index.html",
      },
    },
  },
});
