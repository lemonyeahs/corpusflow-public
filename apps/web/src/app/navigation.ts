import { Activity, Boxes, Database, FileInput, GitBranch, Home, Settings2 } from "lucide-react";
import type { Role } from "../types";

export const ENGINEERS: Role[] = ["admin", "engineer"];
export const REVIEWERS: Role[] = ["admin", "engineer", "reviewer"];
export const navigation = [
  { path: "/home", label: "首页", icon: Home },
  { path: "/data/all", label: "数据台", icon: Boxes },
  { path: "/ingest", label: "数据接入", icon: FileInput, roles: ENGINEERS },
  { path: "/datasets/cpt", label: "CPT 预训练", icon: Database },
  { path: "/datasets/sft", label: "SFT 指令微调", icon: Database },
  { path: "/datasets/dpo", label: "DPO 偏好优化", icon: Database },
  { path: "/lineage", label: "数据血缘", icon: GitBranch },
];
export const advancedNavigation = [
  { path: "/advanced/dashboard", label: "旧版总览", icon: Home },
  { path: "/advanced/ingest", label: "旧版接入", icon: FileInput, roles: ENGINEERS },
  { path: "/advanced/assets", label: "资产中心", icon: Boxes },
  { path: "/advanced/document", label: "文档对照", icon: Boxes },
  { path: "/advanced/processing", label: "处理中心", icon: Activity, roles: ENGINEERS },
  { path: "/advanced/datasets", label: "数据集构建", icon: Database, roles: ENGINEERS },
  { path: "/advanced/dpo", label: "DPO 审核与构建", icon: Database, roles: REVIEWERS },
  { path: "/advanced/lineage", label: "旧版血缘", icon: GitBranch },
  { path: "/advanced/admin", label: "系统管理", icon: Settings2, roles: ["admin"] as Role[] },
];
