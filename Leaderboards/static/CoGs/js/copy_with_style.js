// Optionally log the HTML that we will put on the clipboard, to the console.
const Log_HTML_To_Console = true;

// Optionally a list of classes that, when having styles inlined will when encountered 
// trigger a debugger break (so you can examine the internals in the browsers debugger)
const Classes_To_Debug = []; // "highlight_changes_on"];

function defer_to_UI() { return new Promise(resolve => setTimeout(resolve, 0)); }

// S.B.'s solution for finding CSS rules that match a given element.
//		See: https://stackoverflow.com/a/22638396/4002633
// Made more specific to finding the styles that these CSS rules impact. 
async function CSS_Styles(el, sheets, defer) {
	if (sheets == undefined) sheets = "all";
	if (defer == undefined) defer = true;
	
    let styles = [];
    for (let sheet of document.styleSheets) {
    	try {
	        for (let rule of sheet.cssRules) {
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
	if (defer) await defer_to_UI();
    return styles;
}

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

function add_style(element, rule, explicit_styles) {
	if (explicit_styles == undefined) explicit_styles = [];

    let [n, v] = rule.split(':');
    const N = n == undefined ? '' : n.trim()
    const V = v == undefined ? '' : v.trim()

	if (explicit_styles.includes(N))
        element.style[N] = V;
}

async function inline_style(source_element, target_element) {
	// This gets ALL styles, and generates  HUGE results as there are MANY
    const css = window.getComputedStyle(source_element).cssText;
    const rules = css.split(';');
	const css_matches = await CSS_Styles(source_element);

	if (Classes_To_Debug.length>0)
		for (let Class of Classes_To_Debug)
			if (source_element.classList.contains(Class))
				debugger;

    // Add the user styles we found
    for (let rule of rules)
        add_style(target_element, rule, css_matches);
}

const zip = rows => rows[0].map((_, c) => rows.map(row => row[c]));

// Straight from: https://stackoverflow.com/questions/26336138/how-can-i-copy-to-clipboard-in-html5-without-using-flash/45352464#45352464
function copyStringToClipboard(string) {
    function handler (event){
        event.clipboardData.setData('text/html', string);
        event.preventDefault();
        document.removeEventListener('copy', handler, true);
    }

    document.addEventListener('copy', handler, true);
    document.execCommand('copy');
}

class Copy_With_Style {
	button = null;
	element = null;
	stylesheets = "inline";
	
	// We wrap the nominated element in a div that is not in the DOM. We can copy the wrapper
	// with the element or not. Matters little it's a simple div.'
	copy_wrapper = true;
	
	// If true log the HTML prepared, and the HTML put onto the clpboard to the console, for diagnostic purposes.
	log_HTML_to_console = true;

	// When inlining styles we make a clone of the element to be copied, so we can inline them off DOM.
	// We walk over all the children of the element to be copied using .querySelectorAll('*') and rely
	// on that returning the same elements in the same order for both the original and clone. Empirically
	// this seems reliably to be the case, but I haven't found it documented anywhere that the oder of 
	// elements returned by querySelectorAll is deterministic and consistent. So a check is implemented.
	// Never having seen it fail, we disable it by default. Enabling it adds a little overhead to the copy.   
	check_clone_integrity = false;
	
	constructor(button, element, stylesheets, copy_wrapper) {
		this.button = button;
		this.element = element == undefined ? null : element;
		this.stylesheets = stylesheets == undefined ? "inline" : stylesheets;
		this.copy_wrapper = copy_wrapper == undefined ? true : copy_wrapper;

		this.HTML = null;
		
		this.is_prepared = false;
		this.button.disabled = true; 

		// attach an onclick event to the provided button.
		button.addEventListener("click", this.to_clipboard.bind(this));
	} 
	
	lock() {
		this.is_prepared = false;
		this.button.disabled = true;
	}
	
	
	// This is very slow. 20 seconds for a large leaderboard view. Wow. So currently supports scheduling. But also wants
	// to support letting UI interactions continue. Here is how:
	// https://stackoverflow.com/a/21592778/4002633
	async prepare_copy(element) {
		this.is_being_prepared = true;
		this.element = element == undefined ? this.element : element;

		console.log('copy_with_style.prepare_copy(): Started')
	
	    const clone = this.element.cloneNode(true); // Clone the element we want to copy to the clipboard
	
	    // create a wrapper (that we will try to copy)
	    const wrapper = document.createElement("div");
	    wrapper.id = 'copy_me_with_style';
	
	    if (this.stylesheets == "inline") {
	        const source = this.element.querySelectorAll('*');
	        const target = clone.querySelectorAll('*');
	        const pairs = zip([Array.from(source), Array.from(target)]);
	
	        // Perform an integrity check on the two element lists
	        let cloned_well = true;
			if (this.check_clone_integrity) {
		        for (pair of pairs)
		            if (pair[0].outerHTML !== pair[1].outerHTML)
		                cloned_well = false;
			}
	
	        if (cloned_well) {
				// The inline the styles on those that remain
				for (let pair of pairs)
					if (!hidden(pair[0])) // Don't inline styles on hidden elements, we'll remove them from the clone next
	                	await inline_style(pair[0], pair[1]);
	
				// Remove hidden elements, not needed when styles are inlined
				// When including a <style> element (below) these are still useful
				// as the CSS styles support transitions - like :hover.
				for (let e of target)
					if (hidden(e))
						e.remove();
			}
	    } else if (this.stylesheets instanceof Array) {
	        const style = document.createElement("style");
	        for (let sheet of document.styleSheets) {
	            if (sheet.href && this.stylesheets.includes(basename(sheet.href))) {
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
	    this.HTML = this.copy_wrapper ? wrapper.outerHTML : wrapper.innerHTML;
	
		if (this.log_HTML_to_console) {
	    	console.log("prepare_copy:");
	    	console.log(this.HTML);
		}

		this.button.disabled = false;
		this.is_prepared = true;
		this.is_being_prepared = false;
	}
	
	to_clipboard(event) {
		this.button.disabled = true;

		if (!this.is_prepared) this.prepare_copy(this.element);
		
		const html = this.HTML;
		if (this.log_HTML_to_console) {
	    	console.log("to_clipboard:");
			console.log(html);
		}
		
		copyStringToClipboard(html);
	}
	
	async schedule_handler() {
		if (!this.is_prepared && !this.is_being_prepared && document.readyState === 'complete') {
			// Prepare for a clipboard copy (this is a little slow so we do it only after the tables are fully rednered) 
			console.log('copy_with_style.prepare_copy(): Calling');
			await this.prepare_copy(this.element);
			console.log('copy_with_style.prepare_copy(): Done');
		}
	}

	schedule(element_to_copy) {	
		this.element = element_to_copy;
		document.addEventListener('readystatechange', this.schedule_handler.bind(this));
	} 	
}