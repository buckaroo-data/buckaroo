export default {
  testEnvironment: "jsdom",
  transform: {
    "^.+\\.tsx?$": "ts-jest",
  },

  moduleNameMapper: {
    "\\.(css|less|sass|scss)$": "identity-obj-proxy",
    "^.+\\.svg$": "jest-transformer-svg",
    "^@/(.*)$": "<rootDir>/src/$1",
  },

    testMatch: [
	"!**/*.spec.ts",
	"**/*.test.ts"
    ],
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
};
