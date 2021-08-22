/**
 * Copy With Style. 
 *
 * Provides support of a copy button on a web page that copies a nominated elements true to its rendered style,
 * to the clipboard. Offers th option to include all styles with a <style> tag prefixing the elements outerHTML, 
 * or alternately with a "style" attributes added to each element (the nominate element and all its children),
 * called ""inlining" styles.
 * 
 * Inlining styles (applying them as a "style" attribute one each element) is expensive (slow) and produces more
 * data, conceivably much more data than not inlining them (providing them via a <style> tag), but produuces a copy 
 * that can reliably be emailed. Most email clients today (2021) have patchy or no support for the style tag. 
 * Conversely most email clients respect and render inline style attribvutes faithfully.
 *
 * @link   URL
 * @file   This files defines the Copy_With_Style class.
 * @author Bernd Wechner.
 * @copyright 2001
 * @license Hippocratic License Version Number: 2.1.
 */

class Copy_With_Style {
	element = null;   	// The element to copy to the clipboard (with style!)	
	button = null;    	// The button that, we attach a click even handler to to copy the the element to the clipboard
	mode = null;		// "attribute" (to inline all styles with a "style" attribute on each element) or "tag" (to include a "style" tag)
	progress = null;  	// A progres element that is a sibling or child of the button by default but can be specified explicitly.
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
	
	// Optionally a list of CSS classes that, when having styles inlined will, when encountered 
	// trigger a debugger break (so you can examine the internals in the browser''s debugger)
	// Will only trigger if a debugger is active of course. Pressing F12 in yoru browser will
	// probably bring one up. 
	classes_to_debug = []; // "highlight_changes_on"

	// Optionally a list of styles that, when having styles inlined will, when encountered 
	// trigger a debugger break (so you can examine the internals in the browser''s debugger)
	// Will only trigger if a debugger is active of course. Pressing F12 in yoru browser will
	// probably bring one up. 
	styles_to_debug = []; // "background-color";
	
	// The HTML string (rendition) of element
	HTML = "";
	// The Text string (rendition) of element
	text = "";

	// An internal bail request. Because prepare_copy() defers to UI maintaining an interactive UI a user
	// can mageke changes to element meaning we have to start the perparation again, i.e. bail the one
	// that's running and start again. These flags effect that interation.
	bail = false;   // Set to request a bail
	bailed = false; // Set when the request is honoured
	
    // Write useful tracing info out to console
	debug = true;

    // Write a performance summary to console 
	log_performance = true;
	
	constructor(button, stylesheets, element, mode, copy_wrapper) {
		this.button = button;
		this.stylesheets = stylesheets == undefined ? [] : stylesheets;
		this.element = element == undefined ? null : element;
		this.mode = mode == undefined ? "attribute" : mode;
		this.copy_wrapper = copy_wrapper == undefined ? true : copy_wrapper;
		this.progress = button.parentElement.querySelector("progress"); 

		this.HTML = null;
		this.text = null;
		
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
		if (this.debug) console.log(`prepare_copy started: ${element}`);
		let start = performance.now();
		this.is_being_prepared = true;
		this.element = element == undefined ? this.element : element;
		if (this.progress) {
			this.progress.value = 0;
			this.progress.style.display = "inline";
		}

	    const clone = this.element.cloneNode(true); // Clone the element we want to copy to the clipboard
	
	    // create a wrapper (that we will try to copy)
	    const wrapper = document.createElement("div");
	    wrapper.id = 'copy_me_with_style';

		let nelements = null;
	
	    if (this.mode == "attribute") {
	        const source = this.element.querySelectorAll('*');
	        const target = clone.querySelectorAll('*');
	        const pairs = this.#zip([Array.from(source), Array.from(target)]);

			nelements = pairs.length;
	
	        // Perform an integrity check on the two element lists
	        let cloned_well = true;
			if (this.check_clone_integrity) {
		        for (pair of pairs)
		            if (pair[0].outerHTML !== pair[1].outerHTML)
		                cloned_well = false;
			}

			if (this.log_performance) {
				const done = performance.now();
				const runtime  = done - start;
				const rate1 = runtime/nelements;
				const rate2 = nelements/runtime*1000;
				console.log(`Cloned and prepared ${nelements.toLocaleString()} elements in ${runtime.toLocaleString()} ms, for ${rate1.toLocaleString()} ms/element or ${rate2.toLocaleString()} elements/s`)
				start = performance.now()
			}
	
	        if (cloned_well) {
				// The inline the styles on those that remain
				if (this.progress) this.progress.max = nelements;
				for (let pair of pairs) {
					if (!this.#hidden(pair[0])) // Don't inline styles on hidden elements, we'll remove them from the clone next
	                	await this.inline_style(pair[0], pair[1]);
					if (this.progress) this.progress.value++;
					if (this.bail) {
					 	if (this.debug) console.log("Bailing ...");
						break;
					}
					await this.defer_to_UI();
				}
				
				if (this.log_performance) {
					const done = performance.now();
					const runtime  = done - start;
					const rate1 = runtime/nelements;
					const rate2 = nelements/runtime*1000;
					console.log(`Inlined styles on ${nelements.toLocaleString()} elements in ${runtime.toLocaleString()} ms, for ${rate1.toLocaleString()} ms/element or ${rate2.toLocaleString()} elements/s`)
					start = performance.now()
				}
	
				if (!this.bail)
					// Remove hidden elements, not needed when styles are inlined
					// When including a <style> element (below) these are still useful
					// as the CSS styles support transitions - like :hover.
					for (let e of target)
						if (this.#hidden(e))
							e.remove();

				if (this.log_performance) {
					const done = performance.now();
					const runtime  = done - start;
					const rate1 = runtime/nelements;
					const rate2 = nelements/runtime*1000;
					console.log(`Removed hidden elements from ${nelements.toLocaleString()} elements in ${runtime.toLocaleString()} ms, for ${rate1.toLocaleString()} ms/element or ${rate2.toLocaleString()} elements/s`)
					start = performance.now()
				}
			}
	    } else if (this.mode == "tag") {
	        const style = document.createElement("style");
	        for (let sheet of document.styleSheets) {
	            if (sheet.href && (this.stylesheets.length==0 || this.stylesheets.includes(this.#basename(sheet.href)))) {
	                let rules = [];
	                for (rule of sheet.cssRules) rules.push(rule.cssText)
	
	                style.append(rules.join('\n'));
	            }
	        }
	
	        wrapper.append(style);
	    }

		if (!this.bail) {	
		    // Add the cloned element to the wrapper 	
		    wrapper.append(clone);
		
		    // Grab the HTML
		    this.HTML = this.copy_wrapper ? wrapper.outerHTML : wrapper.innerHTML;

		    // Grab the Text. Chrome provides innerText and outertext. Firefox only innerText. Both look the
			// same on chrome to me. 
			this.text = element.innerText;
		
			if (this.log_HTML_to_console) {
		    	console.log("prepare_copy HTML:");
		    	console.log(this.HTML);
		    	console.log("prepare_copy text:");
		    	console.log(this.text);
			}
		}

		this.button.disabled = false;
		this.is_prepared = true;
		this.is_being_prepared = false;
		if (this.progress) this.progress.style.display = "none";
		if (this.bail) {
			this.bail = false;
			this.bailed = true;
		 	if (this.debug) console.log("Bailed ...");
		};
	}
	
	to_clipboard() {
		if (!this.is_prepared) this.prepare_copy(this.element);

		this.button.disabled = true;
		
		if (this.log_HTML_to_console) {
	    	console.log("to_clipboard HTML:");
			console.log(this.HTML);
	    	console.log("to_clipboard text:");
	    	console.log(this.text);
		}
		
		this.#copy_to_clipboard();
		this.button.disabled = false;
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
	defer_to_UI(how_long) {
		if (how_long == undefined) how_long = 0; 
		return new Promise(resolve => setTimeout(resolve, how_long));
	}
	
	// S.B.'s solution for finding CSS rules that match a given element.
	//		See: https://stackoverflow.com/a/22638396/4002633
	// Made more specific to finding the styles that these CSS rules impact.  
	async CSS_Styles(el, sheets) {
		if (sheets == undefined) sheets = "all";
		
	    let styles = [];
		
		// First get the style attribute
		const style_attr = el.getAttribute("style");
		if (style_attr) {
			const attr_styles = style_attr.split(';');
			for (let rule of attr_styles) 
				if (rule) {
				    const [n, v] = rule.split(':');
				    const N = n == undefined ? '' : n.trim()
				    const V = v == undefined ? '' : v.trim()
					styles.push(N);
				}
		}
		
		// Then match the class attribute defined styles
	    for (let sheet of document.styleSheets) {
			if (sheet.href && (this.stylesheets.length==0 || this.stylesheets.includes(this.#basename(sheet.href))))
		    	try {
			        for (let rule of sheet.cssRules) {
			            if (el.matches(rule.selectorText)) {
							const new_styles = Array.from(rule.style).filter(s => !styles.includes(s));
							styles.push(...new_styles);
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
		const cs = window.getComputedStyle(source_element);
		const css_matches = await this.CSS_Styles(source_element);

		let debug_class = false;
		if (this.classes_to_debug.length>0) {
			for (let Class of this.classes_to_debug)
				if (source_element.classList.contains(Class))
					debug_class = true;
		}

		if (debug_class) 
			debugger;

	    // Add the user styles we found
		for (let r=0; r<cs.length; r++) 
			if (css_matches.includes(cs.item(r)))
				target_element.style[cs.item(r)] = cs.getPropertyValue(cs.item(r));
	}
	
	// Straight from: https://stackoverflow.com/questions/26336138/how-can-i-copy-to-clipboard-in-html5-without-using-flash/45352464#45352464
	#copy_to_clipboard() {
	    function handler(event){
	        event.clipboardData.setData('text/html', this.HTML);
	        event.clipboardData.setData('text/plain', this.text);
	        event.preventDefault();
	        document.removeEventListener('copy', handler, true);
	    }
	
	    document.addEventListener('copy', handler.bind(this), true);
	    document.execCommand('copy');
	}
	
	schedule(element_to_copy) {
		if (element_to_copy != undefined) this.element = element_to_copy;
		
		async function handler() {
			if (!this.is_prepared && !this.is_being_prepared && document.readyState === 'complete') {
				// watch element for changes (as we need to prepare_copy() again)
				this.observe_element()
				await this.prepare_copy(this.element);
			}
		}
		
		if (this.element)
			document.addEventListener('readystatechange', handler.bind(this));
	}

	observer = new MutationObserver(this.mutation_handler.bind(this));
		
	// Enable or disable observations on the element to trigger new clipbpboard preparations.
	observe_element(yesno) {
		if (yesno == undefined) yesno = true;
		if (this.debug) console.log(`observe_element: ${yesno}`);
		
		if (yesno)
			this.observer.observe(this.element, {subtree:true, childList: true, attributes: true, attributeOldValue: true, characterData: true,characterDataOldValue: true});
		else if (this.observer)
			this.observer.disconnect();
	} 
	
	// A handler attached to this.element. When this.element changes, we can bail on any 
	// existing preparations and restarte.
	async mutation_handler(mutations) {
		const fingerprint = performance.now(); 
		if (this.debug) console.log(`${fingerprint} mutation: readystate is ${document.readyState}`);

		// If prepare_copy() is running and is not complete  		
		if (this.is_being_prepared) {
			// if it's already been asked to bail, kick back and let it
			if (this.bail) {
				if (this.debug) console.log(`${fingerprint} Already bailing ... let it be.`);
				// Let it act on the signal and bail request
				await this.defer_to_UI(); 
			// if it's not already been asked to bail, then ask it to bail
			} else {
				if (this.debug) console.log(`${fingerprint} Requesting bail...`);
				this.bail = true;

				// Let it act on the signal and bail request
				await this.defer_to_UI(); 

				// Check if it did bail!
				if (this.bailed) {
					if (this.debug) console.log(`${fingerprint} Observed bail... `);
					this.bailed = false;					
				} else {
					if (this.debug) console.log(`${fingerprint} REQUESTED BAIL NOT HONORED!`);
				}
			}			
		}

		if (!this.is_being_prepared) {
			if (this.debug) console.log(`${fingerprint} Requesting prepare_copy() ... (this.bail: ${this.bail}, this.bailed: ${this.bailed})`);
			await this.prepare_copy(this.element);
		}
	}
	
	// A simple basename for matching stylesheets
	#basename(str, sep1, sep2) {
	    if (sep1 == undefined) sep1 = '/';
	    if (sep2 == undefined) sep2 = '?';
	    const parts1 = str.split(sep1);
	    const parts2 = parts1[parts1.length - 1].split(sep2);
	    return parts2[0];
	}
	
	// Determine if a given elemnt is hidden. When inlining styles, hidden elements are dropped.
	#hidden(element) {
		return element.style.visibility === "hidden" || element.style.display === "none";
	}
	
	// A teeny function that zips two Arrays together (like Python's zip)
	// See: https://stackoverflow.com/a/10284006/4002633
	#zip = rows => rows[0].map((_, c) => rows.map(row => row[c]));	
}

