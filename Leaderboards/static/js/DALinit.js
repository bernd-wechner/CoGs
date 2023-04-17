/* ===================================================================================
	DAL - Django Autocomplete Light, provides a lovely widget that can be used for
  	building lists of things, like games, leagues, locations etc.

	The DAL widget fetches data from the server. So when a page has a list of IDs,
	and wants to preopulate a DAL widget, we have to tell the widget the IDs and
	and then it wil fetch texts from the server (get the text for the objects of
	those IDs).

	That is asyncronous and might take a moment of time. During which if we try
	to read the contents of the widget in JavaScript we might read it before the
	round trip is complete. To wit, an initialiser is wrtten here, which updates
	the DAL widget and then waits until the round trip is complete.
=================================================================================== */

// An initialiser for Select2 widgets used. Alas not so trivial to set
// as descrribed here:
// https://select2.org/programmatic-control/add-select-clear-items#preselecting-options-in-an-remotely-sourced-ajax-select2
//
// Because we do an ajax call back to get names for PKs and there may be an delay of unknown
// duration before it returns, we can't compare the request with the selector contents to
// determine if a request is needed. So we have to keep track in a global the requests issued
// to refer to those in deciding if we need to issue a request.
let waiting_for = {};
function finished_waiting() {return Object.keys(waiting_for).length === 0};

// Modern JS chicanery ;-)
// TODO: We could do this more cleanly by wrapping the actual ajax request in a promise rather than a timer.
//       await Promise.all([]promise1, promise2, promise3]) woudl wait for them to finish befoe proceeding.
//       this method uses a timer based sleep to check the waiting_for logs of the requests to do same but
//       is a tad klunkier.
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
async function until(fn) { while (!fn()) {	await sleep(10); } }

function Select2Init(selector, values) {
	if (!values) return; // No work to do if no values provided

	const id = selector[0].id;
	const selected = selector.val().map(Number);
	const ordered_values = values.sort(function(a, b){return a-b});

	let request = new Set();
	for (const value of ordered_values)
		// We want to request a value only if it's not currently selected and we're not waiting for it (already requested it)'
		if (!selected.includes(value) && (!(id in waiting_for) || !waiting_for[id].has(value)))
			request.add(value);

	if (request.size > 0) {
		// Be VERY careful here. DAL paginates by default and may not return all of the objects that the q parameter asks for.
		// the all parameter disables that pagination. If this ever does not return all of the requested objects we will end
		// up waiting endlessly on them.
		// TODO: We can escape this weakness by implementing the promises better so as not to use waiting_for
		//	     The trick is, how?
		const URL = url_selector.replace("__MODEL__", selector.prop('name')) + "?all&q=" + Array.from(request).join(",");

		selector.val(null).trigger('change');

		if (!(id in waiting_for)) waiting_for[id] = new Set();

		// Note locally that we've requested it and are waiting for an answer then issue the request
		// (should really be atomic). Bizaare JS syntax for set union using the spread operator (ellipsis)
		waiting_for[id] = new Set([...waiting_for[id], ...request]);
		$.ajax({
		    type: 'GET',
		    url: URL
		}).then(function (data) {
			// data arrives in JSON like:
			// {"results": [{"id": "1", "text": "Bernd", "selected_text": "Bernd"}, {"id": "2", "text": "Blake", "selected_text": "Blake"}], "pagination": {"more": false}}

			for (const result of data.results) {
				// create the option and append to Select2
				var option = new Option(result.text, result.id, true, true);
				selector.append(option);
				// Take note that we're no longer waiting on it (id arrives as string, was stored as int)
				// But we clobber both just in case ;-). Returns false if it didn't delete because it wasn't there, tue if it did.
				// that is fails silently on the redundant call.
				waiting_for[id].delete(result.id); // Value we might have if we got our wires crossed
				waiting_for[id].delete(parseInt(result.id)); // Expected value
			}
			selector.trigger('change');

			if (waiting_for[id].size === 0) {
				delete waiting_for[id]; // If the set is empty remove the entry in the dict
			}

		    // manually trigger the `select2:select` event
		    //selector.trigger({
		    //    type: 'select2:select',
		    //    params: {
		    //        data: data
		    //    }
		    //});
		});
	}
}
