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
	
	// Optionally a list of CSS classes that, when having styles inlined will when encountered 
	// trigger a debugger break (so you can examine the internals in the browser''s debugger)
	// Will only trigger if a debugger is active of course. Pressing F12 in yoru browser will
	// probably bring one up. 
	classes_to_debug = []; // "highlight_changes_on"];	
	
	constructor(button, element, stylesheets, copy_wrapper) {
		this.button = button;
		this.element = element == undefined ? null : element;
		this.stylesheets = stylesheets == undefined ? "inline" : stylesheets;
		this.copy_wrapper = copy_wrapper == undefined ? true : copy_wrapper;
		this.progress = button.parentElement.querySelector("progress"); // is null if no progressbar TODO: make this s sibling of button not a child.

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
		const start = performance.now();
		this.is_being_prepared = true;
		this.element = element == undefined ? this.element : element;
		if (this.progress) this.progress.style.display = "inline";

	    const clone = this.element.cloneNode(true); // Clone the element we want to copy to the clipboard
	
	    // create a wrapper (that we will try to copy)
	    const wrapper = document.createElement("div");
	    wrapper.id = 'copy_me_with_style';

		let nelements = null;
	
	    if (this.stylesheets == "inline") {
	        const source = this.element.querySelectorAll('*');
	        const target = clone.querySelectorAll('*');
	        const pairs = zip([Array.from(source), Array.from(target)]);

			nelements = pairs.length;
	
	        // Perform an integrity check on the two element lists
	        let cloned_well = true;
			if (this.check_clone_integrity) {
		        for (pair of pairs)
		            if (pair[0].outerHTML !== pair[1].outerHTML)
		                cloned_well = false;
			}
	
	        if (cloned_well) {
				// The inline the styles on those that remain
				if (this.progress) this.progress.max = nelements;
				for (let pair of pairs) {
					if (!hidden(pair[0])) // Don't inline styles on hidden elements, we'll remove them from the clone next
	                	await this.inline_style(pair[0], pair[1]);
					if (this.progress) this.progress.value++;
					await this.defer_to_UI();
				}
	
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
		if (this.progress) this.progress.style.display = "none";
		const done = performance.now();
		const runtime  = done - start;
		const rate1 = runtime/nelements;
		const rate2 = nelements/runtime*1000;
		console.log(`Processed ${nelements} elements in ${runtime.toFixed()} ms, for ${rate1.toFixed()} ms/element or ${rate2.toFixed()} elements/s`)
	}
	
	to_clipboard() {
		if (!this.is_prepared) this.prepare_copy(this.element);

		this.button.disabled = true;
		
		const html = this.HTML;
		if (this.log_HTML_to_console) {
	    	console.log("to_clipboard:");
			console.log(html);
		}
		
		this.copy_html_to_clipboard(html);
		this.button.disabled = false;
	}
	
	async schedule_handler() {
		if (!this.is_prepared && !this.is_being_prepared && document.readyState === 'complete') {
			// Prepare for a clipboard copy (this is a little slow so we do it only after the tables are fully rednered) 
			await this.prepare_copy(this.element);
		}
	}

	schedule(element_to_copy) {	
		this.element = element_to_copy;
		document.addEventListener('readystatechange', this.schedule_handler.bind(this));
	}

	// Adds the styles from a CSS rule to the style tag of an element.
	// if a list of explicit styles is provided only styles from that 
	// list are added. This is essentially to avoid adding all the styles
	// that the CSS rule defines, to the style attribute. If no list is 
	// provided they will all be added.  
	add_style(element, rule, explicit_styles) {
		if (explicit_styles == undefined) explicit_styles = null;
	
	    let [n, v] = rule.split(':');
	    const N = n == undefined ? '' : n.trim()
	    const V = v == undefined ? '' : v.trim()
	
		if (!explicit_styles || explicit_styles.includes(N))
	        element.style[N] = V;
	}
	
	// This is a Javascript oddity.
	// See: https://stackoverflow.com/a/60149544/4002633
	// setTimeout runs a function after a given time (specified in ms).
	// In a promise with not resolve callback (.then()) defined it can be called
	// with effectively a null function. With a 0 time into the future, it returns
	// more or less immediately BUT, the key thing to not is the Javascript single
	// threaded idiosyncracy .. and that setTimeout() is the one known method of 
	// yielfing control for a moment to the event loop so that UI events can continue
	// to be handled. To wit, this mysterious little line of code, permits means the 
	// UI remains responsive if it is called from time to time.
	defer_to_UI() { return new Promise(resolve => setTimeout(resolve, 0)); }
	
	// S.B.'s solution for finding CSS rules that match a given element.
	//		See: https://stackoverflow.com/a/22638396/4002633
	// Made more specific to finding the styles that these CSS rules impact.  
	async CSS_Styles(el, sheets) {
		if (sheets == undefined) sheets = "all";
		
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
	    return styles;
	}
	
	async inline_style(source_element, target_element) {
		// This gets ALL styles, and generates  HUGE results as there are MANY
	    const css = window.getComputedStyle(source_element).cssText;
	    const rules = css.split(';');
		const css_matches = await this.CSS_Styles(source_element);
		const classes_to_debug = [];
	
		if (classes_to_debug.length>0)
			for (let Class of Classes_To_Debug)
				if (source_element.classList.contains(Class))
					debugger;
	
	    // Add the user styles we found
	    for (let rule of rules)
	        this.add_style(target_element, rule, css_matches);
	}
	
	// Straight from: https://stackoverflow.com/questions/26336138/how-can-i-copy-to-clipboard-in-html5-without-using-flash/45352464#45352464
	copy_html_to_clipboard(string) {
	    function handler (event){
	        event.clipboardData.setData('text/html', string);
	        event.preventDefault();
	        document.removeEventListener('copy', handler, true);
	    }
	
	    document.addEventListener('copy', handler, true);
	    document.execCommand('copy');
	}
}

// A simple basename for matching stylesheets
function basename(str, sep1, sep2) {
    if (sep1 == undefined) sep1 = '/';
    if (sep2 == undefined) sep2 = '?';
    const parts1 = str.split(sep1);
    const parts2 = parts1[parts1.length - 1].split(sep2);
    return parts2[0];
}

// Determine if a given elemnt is hidden. When inlining styles, hidden elements are dropped.
function hidden(element) {
	return element.style.visibility === "hidden" || element.style.display === "none";
}

// A teeny function that zips two Arrays together (like Python's zip)
// See: https://stackoverflow.com/a/10284006/4002633
const zip = rows => rows[0].map((_, c) => rows.map(row => row[c]));

