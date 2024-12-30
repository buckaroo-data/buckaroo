const BUCKAROO_STYLE_ID = "buckaroo-style-block";
export const injectBuckarooCSS = (css_text:string) => {
    if(document.getElementById(BUCKAROO_STYLE_ID) !== null) {
        return
    }

	let style = Object.assign(document.createElement("style"), {
		id: BUCKAROO_STYLE_ID,
		type: "text/css"
	});
	style.appendChild(document.createTextNode(css_text));
	document.head.appendChild(style);
}
