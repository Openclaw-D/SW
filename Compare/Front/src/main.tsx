import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ProjectExperience } from "./ProjectExperience";
import "./styles/tokens.css";
import "./styles/app.css";

const root = document.getElementById("root");
if (!root) throw new Error("缺少应用挂载节点");

createRoot(root).render(
  <StrictMode>
    <ProjectExperience />
  </StrictMode>,
);
