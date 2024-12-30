import { useState } from "react";


export const SampleButton = (
    {label, onClick}:
    {label:string; onClick:(ev:any) => void;}) => {
    return <button onClick={onClick}>{label}</button>
}

export const HeaderNoArgs = () => {
	return <h1> Header NoArgs </h1>
}

export const IncrementButton = ({value, setValue }:{value:number, setValue:any}) => {

    const bClick = () => {
	setValue(value + 1)
    }
    return <button onClick={bClick}>{value}</button>
}

export const Counter = () => {
    const [count, setCount] = useState(1);

    return (<div>
	<IncrementButton value={count} setValue={setCount} />
	<IncrementButton value={count} setValue={setCount} />
	</div>
	)


}

