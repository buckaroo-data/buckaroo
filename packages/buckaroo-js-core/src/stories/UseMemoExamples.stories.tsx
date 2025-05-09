import {useState, useMemo } from "react";
import type { Meta, StoryObj } from "@storybook/react";


const SubSubComponent = ({ errorString }: { errorString: string }) => {
    console.log("SubSub , rendered", errorString);
    return (<h3>{errorString}</h3>)
}

const SubComponent = (
    { headerName,
        error }
        : {
            headerName: string,
            error: string
        }
) => {
    console.log("SubComponent, rendered", headerName);
    const outerStyle = useMemo( ()=>  {
        console.log("inside outerStyle Memo");
        return  { border: "4px solid green" };}, []);
    return (<div style={outerStyle}>
        <h2>{headerName}</h2>
        <SubSubComponent errorString={error} />
    </div>
    );

}
const ControlsWrapper = () => {
    const [useSecondaryConfig, setUseSecondaryConfig] = useState(false);
    const [showError, setShowError] = useState(false);
    const activeConfig = useSecondaryConfig ? "foo" : "bar";
  
    //const [activeCol, setActiveCol] = useState("b");
    const errString = showError ? 'Error' : 'No Error';
    return (
        <div style={{ height: 500, width: 800 }}> 
            <button
              onClick={() => setUseSecondaryConfig(!useSecondaryConfig)}
            >
              Toggle Config
            </button>
            <span>Current Config: {useSecondaryConfig ? 'Secondary' : 'Primary'}</span>
            <button
              onClick={() => setShowError(!showError)}
            >
              Toggle Error
            </button>
            <span>Error State: {errString}</span>
            <SubComponent headerName={activeConfig} error={errString} />
          </div>);
}


const meta = {
    title: "ConceptExamples/UseMemo",
    component: ControlsWrapper,
    parameters: {
        layout: "centered",
    },
    tags: ["autodocs"],
} satisfies Meta<typeof ControlsWrapper>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
    args: {
    },
};

