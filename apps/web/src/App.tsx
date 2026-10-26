import { HashRouter } from "react-router-dom";
import { AuthProvider } from "./app/auth";
import { AppRoutes } from "./app/routes";
import "./styles.css";
import "./ui/theme.css";

export default function App() {
  return <HashRouter><AuthProvider><AppRoutes /></AuthProvider></HashRouter>;
}
