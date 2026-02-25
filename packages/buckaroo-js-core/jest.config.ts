export default {
  testEnvironment: "jsdom",
  transform: {
    "^.+\\.tsx?$": "ts-jest",
  },

  moduleNameMapper: {
    "\\.(css|less|sass|scss)$": "identity-obj-proxy",
    "^.+\\.svg$": "jest-transformer-svg",
    "^@testing-library/jest-dom$": "<rootDir>/src/test-utils/jest-dom-shim.ts",
    "^react$": "<rootDir>/node_modules/react/index.js",
    "^react/jsx-runtime$": "<rootDir>/node_modules/react/jsx-runtime.js",
    "^react/jsx-dev-runtime$": "<rootDir>/node_modules/react/jsx-dev-runtime.js",
    "^react-dom$": "<rootDir>/node_modules/react-dom/index.js",
    "^react-dom/client$": "<rootDir>/node_modules/react-dom/client.js",
    "^@/(.*)$": "<rootDir>/src/$1",
  },

  testMatch: ["!**/*.spec.ts", "**/*.test.ts", "**/*.test.tsx"],
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
};
