package service

import (
	"regexp"
	"strconv"
	"strings"
)

var (
	ipRegex        = regexp.MustCompile(`\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b`)
	domainRegex    = regexp.MustCompile(`\b([a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+\.[a-zA-Z]{2,})\b`)
	underscoreDom  = regexp.MustCompile(`\b([a-zA-Z0-9][-a-zA-Z0-9_]*(\.[a-zA-Z0-9][-a-zA-Z0-9_]*)*\.[a-zA-Z]{2,})\b`)
	md5Regex       = regexp.MustCompile(`\b([a-fA-F0-9]{32})\b`)
	prefixDevRegex = regexp.MustCompile(`\b((?:LAPTOP|SRV|PC|WIN|SERVER|DESKTOP|WS)[-_][A-Za-z0-9]{2,})\b`)
	hexDevRegex    = regexp.MustCompile(`\b([0-9A-Fa-f]{8}[-][0-9A-Fa-f]{4}[-][0-9A-Fa-f]{4}[-][0-9A-Fa-f]{4}[-][0-9A-Fa-f]{12})\b`)
	ipPortRegex    = regexp.MustCompile(`\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[:：](\d+)\b`)
	urlRegex       = regexp.MustCompile(`https?://[^\s<>"']{2,}`)
)

// isDeviceContext checks if a 32-hex string appears in a device-ID context.
// Device IDs in this system are 32-char hex strings (like MD5 format).
// We consider a 32-hex value a device ID unless it's preceded by "md5" or "hash" keywords.
func isDeviceContext(text string, matchStart int) bool {
	// Look at the 30 chars before the match for device/md5 context clues
	start := matchStart - 30
	if start < 0 {
		start = 0
	}
	context := strings.ToLower(text[start:matchStart])
	// If preceded by "md5", "hash", "file", "样本" — it's likely a file hash
	if strings.Contains(context, "md5") || strings.Contains(context, "hash") ||
		strings.Contains(context, "file") || strings.Contains(context, "样本") {
		return false
	}
	return true
}

// IOCItem extracted indicator of compromise
type IOCItem struct {
	Value string `json:"target"`
	Port  string `json:"port"`
	Type  string `json:"type"` // ip, domain, md5, device, url
}

// IOCExtractor extracts IOCs from free-form text
type IOCExtractor struct{}

func NewIOCExtractor() *IOCExtractor { return &IOCExtractor{} }

// ExtractIOCs 从文本中提取所有 IOC
func (e *IOCExtractor) ExtractIOCs(text string) []IOCItem {
	if text == "" {
		return nil
	}
	seen := make(map[string]bool)
	seenDevice := make(map[string]bool)
	var results []IOCItem

	add := func(item IOCItem) {
		key := item.Value + ":" + item.Port
		if !seen[key] {
			seen[key] = true
			results = append(results, item)
			if item.Type == "device" {
				seenDevice[item.Value] = true
			}
		}
	}

	// IP:Port first
	for _, m := range ipPortRegex.FindAllStringSubmatch(text, -1) {
		ip := m[1]
		port := m[2]
		if isValidIP(ip) {
			add(IOCItem{Value: ip, Port: port, Type: "ip"})
		}
	}

	// Standalone IPs
	for _, m := range ipRegex.FindAllStringSubmatch(text, -1) {
		ip := m[1]
		if isValidIP(ip) {
			already := false
			for _, r := range results {
				if r.Value == ip && r.Type == "ip" {
					already = true
					break
				}
			}
			if !already {
				add(IOCItem{Value: ip, Port: "", Type: "ip"})
			}
		}
	}

	// Domains
	for _, m := range domainRegex.FindAllStringSubmatch(text, -1) {
		domain := m[1]
		if !isCommonDomain(domain) {
			add(IOCItem{Value: domain, Port: "", Type: "domain"})
		}
	}

	// Domains with underscores (e.g. masked_domain_17255.com:53)
	for _, m := range underscoreDom.FindAllStringSubmatchIndex(text, -1) {
		domain := text[m[2]:m[3]]
		port := ""
		// Check text after the domain match for :port
		if m[3] < len(text) && text[m[3]] == ':' {
			end := m[3] + 1
			for end < len(text) && text[end] >= '0' && text[end] <= '9' {
				end++
			}
			if end > m[3]+1 {
				port = text[m[3]+1 : end]
			}
		}
		if !isCommonDomain(domain) && strings.Count(domain, ".") >= 1 {
			add(IOCItem{Value: domain, Port: port, Type: "domain"})
		}
	}

	// Device IDs — extract BEFORE MD5 to avoid overlap (device IDs are 32-hex format)
	// 1. Prefix-based device IDs (LAPTOP-xxx, SRV_xxx, etc.)
	for _, m := range prefixDevRegex.FindAllStringSubmatch(text, -1) {
		add(IOCItem{Value: strings.ToUpper(m[1]), Port: "", Type: "device"})
	}

	// 2. GUID-format device IDs (8-4-4-4-12)
	for _, m := range hexDevRegex.FindAllStringSubmatch(text, -1) {
		add(IOCItem{Value: strings.ToUpper(m[1]), Port: "", Type: "device"})
	}

	// 3. 32-char hex device IDs — check context to distinguish from file hash MD5s
	for _, m := range md5Regex.FindAllStringSubmatchIndex(text, -1) {
		val := text[m[2]:m[3]]
		upperVal := strings.ToUpper(val)
		// Skip if already extracted as a device (prefix/GUID overlap)
		if seenDevice[upperVal] {
			continue
		}
		// Use context analysis: preceded by "md5"/"hash" → file hash; otherwise → device ID
		if isDeviceContext(text, m[2]) {
			add(IOCItem{Value: upperVal, Port: "", Type: "device"})
		}
	}

	// MD5 — only values NOT already classified as devices
	for _, m := range md5Regex.FindAllStringSubmatchIndex(text, -1) {
		val := text[m[2]:m[3]]
		upperVal := strings.ToUpper(val)
		if seenDevice[upperVal] {
			continue
		}
		// Only extract as MD5 if preceded by hash-related keywords
		if !isDeviceContext(text, m[2]) {
			add(IOCItem{Value: upperVal, Port: "", Type: "md5"})
		}
	}

	// URLs
	for _, m := range urlRegex.FindAllString(text, -1) {
		add(IOCItem{Value: m, Port: "", Type: "url"})
	}

	return results
}

func isValidIP(ip string) bool {
	parts := strings.Split(ip, ".")
	if len(parts) != 4 {
		return false
	}
	for _, p := range parts {
		if len(p) == 0 || len(p) > 3 {
			return false
		}
		for _, c := range p {
			if c < '0' || c > '9' {
				return false
			}
		}
		n, _ := strconv.Atoi(p)
		if n < 0 || n > 255 {
			return false
		}
	}
	return true
}

func isCommonDomain(domain string) bool {
	known := []string{
		"www.google.com", "www.baidu.com", "www.microsoft.com",
		"www.apple.com", "www.amazon.com", "www.cloudflare.com",
	}
	lower := strings.ToLower(domain)
	for _, kd := range known {
		if lower == kd {
			return true
		}
	}
	return false
}
