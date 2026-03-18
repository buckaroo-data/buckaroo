export default {
  testEnvironment: "jsdom",
  transform: {
    "^.+\\.tsx?$": "ts-jest",
    "lodash-es.+\\.js$": "ts-jest",
    "hyparquet.+\\.js$": "ts-jest",
  },
  transformIgnorePatterns: ["node_modules/(?!.*(lodash-es|hyparquet))"],

  moduleNameMapper: {
    "\\.(css|less|sass|scss)$": "identity-obj-proxy",
    "^.+\\.svg$": "jest-transformer-svg",
    "^@/(.*)$": "<rootDir>/src/$1",
    "^hyparquet$": "<rootDir>/node_modules/hyparquet/src/index.js",
  },

  testMatch: ["!**/*.spec.ts", "**/*.test.ts", "**/*.test.tsx"],
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
};
