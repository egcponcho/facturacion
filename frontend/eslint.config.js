// Reglas de calidad del frontend: `npm run lint`.
import vue from "eslint-plugin-vue";
import globals from "globals";

export default [
  { ignores: ["dist/**", "node_modules/**", "public/**"] },
  ...vue.configs["flat/essential"],
  {
    files: ["**/*.{js,mjs,vue}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrors: "none" }],
      "no-undef": "error",
      "no-dupe-keys": "error",
      "no-unreachable": "error",
      // Las vistas se nombran por su ruta (EmpresaView, Login…); no exige nombres compuestos.
      "vue/multi-word-component-names": "off",
    },
  },
];
