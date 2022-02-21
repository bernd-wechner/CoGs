function encodeList(list) {
	return encodeURIComponent(list).replace(/%2C/g, ",");
}

function encodeDateTime(datetime) {
	// We communicate datetimes in the ISO 8601 format:
	// https://en.wikipedia.org/wiki/ISO_8601
	// but in URLs they turn into an ugly mess. If we make a few simple URL safe
	// substitutions and unmake them at the server end all is good, and URLs
	// become legible approximations to ISO 8601.
	//
	// ISO 8601 permits TZ offests with and with the : so +10:00 and +1000 are
	// fine, but we are also more flexible and permit a space before the TZ offset
	// and indeed in place of the unsighlty T between date and time in ISO 8601.
	// So in effect we only care about approximating the standard ;-).
	//
	// Of note:
	//
	// + is a standard way to encode a space in URL. Though encodeURIComponent
	// opts for %20.
	//
	// we can use + safely and it arrives at the server as a space.
	//
	// : is encoded as %3A. It turns out : is not a recommended URL character
	// and a reserved character, but it does transport fine at least on Chrome 
	// tests.
	//
	// Still we can substitue - for it and that is a safe legible char already 
	// in use on the dates and can be decoded back to : by the server.
	//
	// The Timezone is introduced by + or -
	//
	// - travels unhindered. Is a safe URL character.
	// + is encoded as %2B, but we can encode it with + which translates to a
	// space at the server, but known we did this it can decdoe the space back
	// to +.
	return encodeURIComponent(datetime).replace(/%20/g, "+").replace(/%3A/g, "-").replace(/%2B/g, "+");
}