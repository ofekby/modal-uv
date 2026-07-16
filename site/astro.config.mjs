import { defineConfig } from "astro/config";
import icon from "astro-icon";

export default defineConfig({
  site: "https://ofekby.github.io",
  base: "/modal-uv",
  output: "static",
  integrations: [icon()],
});
