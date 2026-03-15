export default {
  testEnvironment: "jsdom",
  transform: {
    "^.+\\.tsx?$": "ts-jest",
    "lodash-es.+\\.js$": "ts-jest",
  },
  transformIgnorePatterns: ["node_modules/(?!.*lodash-es)"],

  moduleNameMapper: {
    "\\.(css|less|sass|scss)$": "identity-obj-proxy",
    "^.+\\.svg$": "jest-transformer-svg",
    "^@/(.*)$": "<rootDir>/src/$1",
    "^lodash-es$": "lodash",
  },

  testMatch: ["!**/*.spec.ts", "**/*.test.ts", "**/*.test.tsx"],
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
};
