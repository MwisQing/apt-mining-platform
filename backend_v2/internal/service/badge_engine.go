package service

import (
	"strings"

	"apt-mining-platform/v2/internal/config"
)

// BadgeDef 徽章定义
type BadgeDef struct {
	Name  string
	Label string
	Color string
}

var BadgeRegistry = map[string]BadgeDef{
	"apt_dict":       {Name: "apt_dict", Label: "APT词典", Color: "red"},
	"advanced_crime": {Name: "advanced_crime", Label: "高级黑灰产", Color: "purple"},
	"noise_family":   {Name: "noise_family", Label: "噪声家族", Color: "gray"},
	"multi_vendor":   {Name: "multi_vendor", Label: "多厂商", Color: "yellow"},
	"cross_day":      {Name: "cross_day", Label: "跨天持续", Color: "green"},
	"lateral":        {Name: "lateral", Label: "横向扩散", Color: "blue"},
	"expired_revive": {Name: "expired_revive", Label: "追踪过期", Color: "orange"},
	"high_tier":      {Name: "high_tier", Label: "高级别", Color: "gold"},
	"scan_noise":     {Name: "scan_noise", Label: "疑似扫描", Color: "lightgray"},
}

// VendorCount 计算厂商数量
func VendorCount(vendors string) int {
	if vendors == "" {
		return 0
	}
	count := 0
	for _, v := range strings.Split(vendors, ",") {
		if strings.TrimSpace(v) != "" {
			count++
		}
	}
	return count
}

// SplitValues 分割逗号分隔的值
func SplitValues(s string) []string {
	if s == "" {
		return nil
	}
	var result []string
	for _, v := range strings.Split(s, ",") {
		v = strings.TrimSpace(v)
		if v != "" {
			result = append(result, v)
		}
	}
	return result
}

// IsNoiseFamily 判断威胁类型是否属于噪声家族
func IsNoiseFamily(threatType string, noiseFile string) bool {
	noiseKeywords := []string{"scan", "noise", "benign", "扫描", "噪声", "traffic", "流量"}
	lower := strings.ToLower(threatType)
	for _, kw := range noiseKeywords {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

// GetEnabledBadges 返回当前启用的 badge 集合
func GetEnabledBadges(cfg *config.Config) map[string]bool {
	enabled := make(map[string]bool)
	for _, e := range cfg.Badges.Enabled {
		enabled[e] = true
	}
	return enabled
}
