import { default as React } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
interface ShadowDomWrapperProps {
    children: React.ReactNode;
}
export declare const ShadowDomWrapper: React.FC<ShadowDomWrapperProps>;
type SelectBoxProps<T extends string> = {
    label: string;
    options: T[];
    value: T;
    onChange: (value: T) => void;
};
export declare const SelectBox: <T extends string>({ label, options, value, onChange }: SelectBoxProps<T>) => import("react/jsx-runtime").JSX.Element;
export {};
