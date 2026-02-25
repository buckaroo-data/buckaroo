export {};
declare global {
    namespace jest {
        interface Matchers<R> {
            toBeInTheDocument(): R;
            toHaveClass(...classNames: string[]): R;
        }
    }
}
