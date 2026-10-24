import tseslint from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  { ignores: ["dist/**"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { "@typescript-eslint": tseslint, "react-hooks": reactHooks },
    rules: { ...tseslint.configs.recommended.rules, "react-hooks/rules-of-hooks": "error", "react-hooks/exhaustive-deps": "off" },
  },
];
