package service

import (
	"regexp"
	"strconv"
	"strings"
)

var (
	ipRegex       = regexp.MustCompile(`\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b`)
	domainRegex   = regexp.MustCompile(`\b([a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+\.[a-zA-Z]{2,})\b`)
	md5Regex      = regexp.MustCompile(`\b([a-fA-F0-9]{32})\b`)
	deviceIDRegex = regexp.MustCompile(`\b((?:LAPTOP|SRV|PC|WIN|SERVER|DESKTOP|WS)[-_][A-Za-z0-9]+)\b`)
	ipPortRegex   = regexp.MustCompile(`\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[:：](\d+)\b`)
	urlRegex      = regexp.MustCompile(`https?://[^\s<>"']{2,}`)
)

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
	var results []IOCItem

	add := func(item IOCItem) {
		key := item.Value + ":" + item.Port
		if !seen[key] {
			seen[key] = true
			results = append(results, item)
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

	// MD5
	for _, m := range md5Regex.FindAllStringSubmatch(text, -1) {
		add(IOCItem{Value: m[1], Port: "", Type: "md5"})
	}

	// Device IDs
	for _, m := range deviceIDRegex.FindAllStringSubmatch(text, -1) {
		add(IOCItem{Value: strings.ToUpper(m[1]), Port: "", Type: "device"})
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
