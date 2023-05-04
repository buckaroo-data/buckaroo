module.exports = {
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/eslint-recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:prettier/recommended'
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    project: "tsconfig.json",
    sourceType: 'module'
  },
    plugins: ['@typescript-eslint',
	      'prettier'
	     ],
  rules: {
    '@typescript-eslint/no-unused-vars': ['warn', { args: 'none' }],
    '@typescript-eslint/no-explicit-any': 'off',
    '@typescript-eslint/no-namespace': 'off',
    '@typescript-eslint/no-use-before-define': 'off',
    "@typescript-eslint/no-unused-vars": "off",

    //necessary for js/version.ts... otherwise the python build fails
    "@typescript-eslint/no-var-requires": "off",


    "@typescript-eslint/explicit-function-return-type": "off",
    '@typescript-eslint/quotes': [
      'error',
      'single',
      { avoidEscape: true, allowTemplateLiterals: false }
    ],
    curly: ['error', 'all'],
    eqeqeq: 'error',
    'prefer-arrow-callback': 'error'
  },
    "ignorePatterns": [
        "webpack.config.ts",
        "jest.config.js"
    ]
};
