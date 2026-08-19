import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ShowcaseExperience } from "./ShowcaseExperience";
import { PUBLIC_LOCALE_KEY } from "./lib/publicLocale";
import "./styles/tokens.css";
import "./styles/app.css";
import "./styles/showcase-entry.css";

localStorage.setItem(PUBLIC_LOCALE_KEY, "zh-CN");
document.documentElement.lang = "zh-CN";

const root = document.getElementById("root");
if (!root) throw new Error("缺少展示入口挂载节点");

createRoot(root).render(
  <StrictMode>
    <ShowcaseExperience />
  </StrictMode>,
);
