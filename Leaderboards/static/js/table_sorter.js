// A simple table sorter that can be attached to a table as an eventlistener as follows;
//
//     document.addEventListener('DOMContentLoaded', TableSorter(tableid));
//
// Based on:
// 		https://github.com/1milligram/html-dom/blob/master/public/demo/sort-a-table-by-clicking-its-headers/index.html

function TableSorter(table_id) {
	const table = document.getElementById(table_id);
	const headers = table.querySelectorAll('th');
	const tableBody = table.querySelector('tbody');
	const rows = tableBody.querySelectorAll('tr');

	// Track sort directions
	const directions = Array.from(headers).map(function(header) {
		return '';
	});

	// Transform the content of given cell in given column
	const transform = function(index, content) {
		// Get the data type of column
		const type = headers[index].getAttribute('data-type');
		switch (type) {
			case 'number':
				return parseFloat(content);
			case 'duration_phrase':
				const parts = content.match(/(\d+(\s|&nbsp;)\w+)/g);
				let value = 0;
				if (parts != null && typeof parts[Symbol.iterator] === 'function')
					for (let part of parts) {
						const clean = part.replace(/(\s|&nbsp;)/g, " ")
						const [val, unit] = clean.split(" ");
						switch (unit) {
							case 'millisecond':
							case 'milliseconds':
								value += val;
								break;
							case 'microsecond':
							case 'microseconds':
								value += val * 1000;
								break;
							case 'second':
							case 'seconds':
								value += val * 1000 * 1000;
								break;
							case 'minute':
							case 'minutes':
								value += val * 1000 * 1000 * 60;
								break;
							case 'hour':
							case 'hours':
								value += val * 1000 * 1000 * 60 * 60;
								break;
							case 'day':
							case 'days':
								value += val * 1000 * 1000 * 60 * 60 * 24;
								break;
							case 'week':
							case 'weeks':
								value += val * 1000 * 1000 * 60 * 60 * 24 * 7;
								break;
							case 'month':
							case 'months':
								value += val * 1000 * 1000 * 60 * 60 * 24 * 365.25 / 12; // Approximate
								break;
							case 'year':
							case 'years':
								value += val * 1000 * 1000 * 60 * 60 * 24 * 365.25; // Approximate
								break;
						}
					}
				return value;
				break;
			case 'date':
				return Date.parse(content);
			case 'string':
			default:
				return content;
		}
	};

	const getContent = function(element) {
		if (element.children.length === 1 && element.children[0].tagName === "DETAILS") {
			return element.children[0].getElementsByTagName("SUMMARY")[0].innerText;
		} else {
			return element.innerText;
		}
	}

	const sortColumn = function(index) {
		// Get the current direction
		const direction = directions[index] || 'asc';

		// A factor based on the direction
		const multiplier = direction === 'asc' ? 1 : -1;

		const newRows = Array.from(rows);

		newRows.sort(function(rowA, rowB) {
			const cellA = getContent(rowA.querySelectorAll('td')[index]);
			const cellB = getContent(rowB.querySelectorAll('td')[index]);

			const a = transform(index, cellA);
			const b = transform(index, cellB);

			switch (true) {
				case a > b:
					return 1 * multiplier;
				case a < b:
					return -1 * multiplier;
				case a === b:
					return 0;
			}
		});

		// Remove old rows
		[].forEach.call(rows, function(row) {
			tableBody.removeChild(row);
		});

		// Reverse the direction
		directions[index] = direction === 'asc' ? 'desc' : 'asc';

		// Append new row
		newRows.forEach(function(newRow) {
			tableBody.appendChild(newRow);
		});
	};

	[].forEach.call(headers, function(header, index) {
		header.addEventListener('click', function() {
			sortColumn(index);
		});
	});
};
