// Webkit styles tend to pollute style inlining. Not sure how or why they
// escape Emile Perron User style extraction filter, but they do. 
// Also empirically testing htis a whole load of seemingly irrelevant styles 
// still sneak through. So an ignore list based on a look at stuff I've tested.
const Styles_To_Ignore = [/-webkit-.*/, 
                          /.*-origin/, 
                          /padding-block/,
                          /padding-inline/,
                          /block-size/, 
                          /inline-size/,
                          /border-block-.*/, 
                          /border-inline-.*/];


// Optionally a list of classes that, when having styles inlined will when encountered 
// trigger a debugger break (so you can examine the internals in the browsers debugger)
const Classes_To_Debug = []; // "highlight_changes_on"];

// When inlining styles we make a clone of the element to be copied, so we can inline them off DOM.
// We walk over all the children of the element to be copied using .querySelectorAll('*') and rely
// on that returning the same elements in the same order for both the original and clone. Empirically
// this seems reliably to be the case, but I haven't found it documented anywhere that the oder of 
// elements returned by querySelectorAll is deterministic and consistent. So a check is implemented.
// Never having seen it fail, we disable it by default. Enabling it adds a little overhead to the copy.   
const Check_Clone_Integrity = false;

// Optionally log the HTML that we will put on the clipboard, to the console.
const Log_HTML_To_Console = true;


// S.B.'s solution for finding CSS rules that match a given element.
//		See: https://stackoverflow.com/a/22638396/4002633
// Made more specific to finding the styles that these CSS rules impact. 
function CSS_Styles(el) {
    let styles = [];

    el.matches = el.matches || el.webkitMatchesSelector || el.mozMatchesSelector || el.msMatchesSelector || el.oMatchesSelector;

    for (let sheet of document.styleSheets) {
    	try {
            const rules = sheet.rules || sheet.cssRules;
	        for (let rule of rules) {
	            if (el.matches(rule.selectorText)) {
					const rule_styles = Array.from(rule.styleMap.keys());
					for (let s of rule_styles)
						if (!styles.includes(s))
							styles.push(s); 
	            }
	        }
    	} 
    	catch(err) {
			// CORS errors land here
			// To avoid them, make sure on cross origin (CDN) style sheet links to include 
			// 		crossorigin="anonymous" referrerpolicy="no-referrer" 
			console.log(`Failed to get rules from: ${sheet.href}\n${err}`)
    	}

    }
    return styles;
}

// Emile Perron's solution to finding applied styles as distinct from default browser styles
//     See: https://stackoverflow.com/a/56408175/4002633
class Computed_Styles {
    // Returns a dummy iframe with no styles or content
    // This allows us to get default styles from the browser for an element
    static getStylesIframe() {
        if (typeof window.blankIframe != 'undefined') {
            return window.blankIframe;
        }

        window.blankIframe = document.createElement('iframe');
        document.body.appendChild(window.blankIframe);

        return window.blankIframe;
    }

    // Turns a CSSStyleDeclaration into a regular object, as all values become "" after a node is removed
    static getStylesObject(node, parentWindow) {
        const styles = parentWindow.getComputedStyle(node);
        let stylesObject = {};

        for (let i = 0; i < styles.length; i++) {
            const property = styles[i];
            stylesObject[property] = styles[property];
        }

        return stylesObject;
    }

    // Returns a styles object with the browser's default styles for the provided node
    static getDefaultStyles(node) {
        let iframe = this.getStylesIframe();
        let iframeDocument = iframe.contentDocument;

    	if (iframeDocument == null) {
			// Try again
			iframe = this.getStylesIframe();
			iframeDocument = iframe.contentDocument;
			debugger; // No idea why this keeps happening
		}

        const targetElement = iframeDocument.createElement(node.tagName);

        iframeDocument.body.appendChild(targetElement);
        const defaultStyles = this.getStylesObject(targetElement, iframe.contentWindow);

        targetElement.remove();

        return defaultStyles;
    }

    // Returns a styles object with only the styles applied by the user's CSS that differ from the browser's default styles
    static getUserStyles(node) {
        const defaultStyles = this.getDefaultStyles(node);
        const styles = this.getStylesObject(node, window);
        let userStyles = {};

        for (let property in defaultStyles) {
            if (styles[property] != defaultStyles[property]) {
                userStyles[property] = styles[property];
            }
        }

        return userStyles;
    }
};

// A simple basename for matching stylesheets
function basename(str, sep1, sep2) {
    if (sep1 == undefined) sep1 = '/';
    if (sep2 == undefined) sep2 = '?';
    const parts1 = str.split(sep1);
    const parts2 = parts1[parts1.length - 1].split(sep2);
    return parts2[0];
}

function hidden(element) {
	return element.style.visibility === "hidden" || element.style.display === "none";
}

function add_style(element, rule, styles_to_ignore, explicit_styles) {
    if (styles_to_ignore == undefined) styles_to_ignore = Styles_To_Ignore;
	if (explicit_styles == undefined) explicit_styles = [];

    let x = 1;
    let [n, v] = rule.split(':');
    const N = n == undefined ? '' : n.trim()
    const V = v == undefined ? '' : v.trim()

    // A quick filter on styles we don't want to inline
    function ignore_style(style) {
        for (ignore of styles_to_ignore) if (style.match(ignore)) return true; 
        return false;
    }

    //if (V != null && V !== '' && V !== 'inherit' && !ignore_style(N))
	if (explicit_styles.includes(N))
        element.style[N] = V;
}

function inline_style(source_element, target_element, styles_to_ignore) {
    if (styles_to_ignore == undefined) styles_to_ignore = Styles_To_Ignore;

	// This gets ALL styles, and generates  HUGE results as there are MANY
    //const css = window.getComputedStyle(source_element).cssText;
    //const rules = css.split(';');

	// This pulls a trick to fin styles that deviate from defaults.  
	const css = Computed_Styles.getUserStyles(source_element);
	const rules = Array.from(Object.keys(css)).map(key => {return `${key}: ${css[key]}`}); 

	const css_matches = CSS_Styles(source_element);

	if (Classes_To_Debug.length>0)
		for (let Class of Classes_To_Debug)
			if (source_element.classList.contains(Class))
				debugger;

    // Add the user styles we found
    for (let rule of rules)
        add_style(target_element, rule, styles_to_ignore, css_matches);

    // A quick filter on styles we don't want to inline
    function ignore_style(style) {
        for (ignore of styles_to_ignore) if (style.match(ignore)) return true; 
        return false;
    }

    // Explicitly remove all ignored styles:
	for (let style of target_element.style)
		if (ignore_style(style)) 
			target_element.style[style] = null; 
}

const zip = rows => rows[0].map((_, c) => rows.map(row => row[c]));

// stylesheets should be a list of .css filenames to include as a style tag or the string "inline" to inline them instead.
function copy_with_style(element, stylesheets, copy_wrapper) {
    if (stylesheets == undefined) stylesheets = "inline";
    if (copy_wrapper == undefined) copy_wrapper = true;

    const clone = element.cloneNode(true); // Clone the element we want to copy to the clipboard

    // create a wrapper (that we will try to copy)
    const wrapper = document.createElement("div");
    wrapper.id = 'copy_me_with_style';

    if (stylesheets == "inline") {
        // TODO: inlining the styles as an option
        // Can maybe get all elements under element with .querySelectorAll('*')
        //		https://stackoverflow.com/questions/60142547/i-need-help-using-recursion-to-navigate-every-element-in-the-dom
        // Can get the styles using .getComputedStyle() 
        //		https://www.w3schools.com/jsref/jsref_getcomputedstyle.asp
        // Can maybe set them inline using the styles attr:
        // 		https://www.javascripttutorial.net/javascript-dom/javascript-style/
        const source = element.querySelectorAll('*');
        const target = clone.querySelectorAll('*');

        const pairs = zip([Array.from(source), Array.from(target)]);

        // Perform an integrity check on the two element lists
        let cloned_well = true;
		if (Check_Clone_Integrity) {
	        for (pair of pairs)
	            if (pair[0].outerHTML !== pair[1].outerHTML)
	                cloned_well = false;
		}

        if (cloned_well) {
			// The inline the styles on those that remain
			for (let pair of pairs)
				if (!hidden(pair[0])) // Don't inline styles on hidden elements, we'll remove them from the clone next
                	inline_style(pair[0], pair[1]);

			// Remove hidden elements, not needed when styles are inlined
			// When including a <style> element (below) these are still useful
			// as the CSS styles support transitions - like :hover.
			for (element of target)
				if (hidden(element))
					element.remove();
		}
    } else if (stylesheets instanceof Array) {
        const style = document.createElement("style");
        for (sheet of document.styleSheets) {
            if (sheet.href && stylesheets.includes(basename(sheet.href))) {
                let rules = [];
                for (rule of sheet.cssRules) rules.push(rule.cssText)

                style.append(rules.join('\n'));
            }
        }

        wrapper.append(style);
    }

    // Add the cloned element to the wrapper 	
    wrapper.append(clone);

    // Grab the HTML of the whole wrapper (for diagnostics, and posisbly for some clipboard write method/s)
    const HTML = copy_wrapper ? wrapper.outerHTML : wrapper.innerHTML;

	if (Log_HTML_To_Console)
    	console.log(HTML);

    // A tweak posted here:
    // 	https://stackoverflow.com/a/45352464/4002633
    // And this works perfectly in Firefox and Chromium! Preserves CSS var colours! A stroke of genius!
    function handler(event) {
        //event.clipboardData.setData('text/plain', "Not supported");
        event.clipboardData.setData('text/html', HTML);
        event.preventDefault();
        document.removeEventListener('copy', handler, true);
    }

    document.addEventListener('copy', handler, true);
    document.execCommand('copy');
}