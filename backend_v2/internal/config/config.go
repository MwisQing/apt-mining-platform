package config

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"gopkg.in/yaml.v3"
)

// Config 系统配置结构
type Config struct {
	Paths struct {
		UploadTmp string `yaml:"upload_tmp"`
		DictAPT   string `yaml:"dict_apt"`
		DictCrime string `yaml:"dict_crime"`
		DictNoise string `yaml:"dict_noise"`
	} `yaml:"paths"`
	Rules struct {
		TraceTTLDays          int  `yaml:"trace_ttl_days"`
		DefaultHideTraced     bool `yaml:"default_hide_traced"`
		DefaultHideClosedEvts bool `yaml:"default_hide_closed_events"`
	} `yaml:"rules"`
	Persistence struct {
		MinDaysForCrossDayBadge int `yaml:"min_days_for_cross_day_badge"`
		StrongDays              int `yaml:"strong_days"`
	} `yaml:"persistence"`
	Badges struct {
		Enabled    []string `yaml:"enabled"`
		Thresholds struct {
			MultiVendorMin    int `yaml:"multi_vendor_min"`
			LateralMinTargets int `yaml:"lateral_min_targets"`
			ScanNoiseCount    int `yaml:"scan_noise_count"`
		} `yaml:"thresholds"`
	} `yaml:"badges"`
	Server struct {
		Host          string `yaml:"host"`
		Port          int    `yaml:"port"`
		AutoOpenBrowser bool `yaml:"auto_open_browser"`
	} `yaml:"server"`
}

var (
	cfg      *Config
	cfgOnce  sync.Once
	baseDir  string
	configPath string // track the loaded config file path for saving
)

// Init 设置基准路径并加载配置（必须在 Get() 之前调用）
// path 可以是相对路径或绝对路径，相对路径基于 baseDir 解析
func Init(path string) error {
	// 获取可执行文件所在目录作为基准
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("get executable path: %w", err)
	}
	baseDir = filepath.Dir(exePath)

	if !filepath.IsAbs(path) {
		path = filepath.Join(baseDir, path)
	}
	configPath = path

	cfg, err = Load(path)
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}

	// 允许环境变量覆盖服务器端口（测试模式用）
	if port := os.Getenv("APT_SERVER_PORT"); port != "" {
		if p, err := fmt.Sscanf(port, "%d", &cfg.Server.Port); p == 1 && err == nil {
			// port overridden
		}
	}
	// 允许环境变量覆盖服务器 host
	if host := os.Getenv("APT_SERVER_HOST"); host != "" {
		cfg.Server.Host = host
	}
	// 允许环境变量覆盖上传目录（正式/测试隔离）
	if dir := os.Getenv("APT_UPLOAD_TMP"); dir != "" {
		cfg.Paths.UploadTmp = dir
	}

	return nil
}

// Get 获取全局配置（懒加载单例）
func Get() *Config {
	return cfg
}

// Load 从指定路径加载配置文件
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}

	var c Config
	if err := yaml.Unmarshal(data, &c); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	return &c, nil
}

// BaseDir 获取基准目录（可执行文件所在目录）
func BaseDir() string {
	return baseDir
}

// ResolvePath 将相对路径解析为绝对路径（基于基准目录）
func ResolvePath(p string) string {
	if filepath.IsAbs(p) {
		return p
	}
	return filepath.Join(baseDir, p)
}

// Save 将当前配置写回 YAML 文件
func Save() error {
	data, err := yaml.Marshal(cfg)
	if err != nil {
		return fmt.Errorf("marshal config: %w", err)
	}
	return os.WriteFile(configPath, data, 0644)
}

var (
	dictCache   = make(map[string]map[string]string)
	dictCacheMu sync.RWMutex
)

// GetDict retrieves a cached dictionary, loading from disk if needed.
func GetDict(path string) map[string]string {
	dictCacheMu.RLock()
	if d, ok := dictCache[path]; ok {
		dictCacheMu.RUnlock()
		return d
	}
	dictCacheMu.RUnlock()
	return LoadDictFile(path)
}

// LoadDictFile reads a YAML dictionary file and caches it.
func LoadDictFile(path string) map[string]string {
	absPath := ResolvePath(path)
	data, err := os.ReadFile(absPath)
	if err != nil {
		return map[string]string{}
	}
	var result map[string]string
	if err := yaml.Unmarshal(data, &result); err != nil {
		return map[string]string{}
	}
	dictCacheMu.Lock()
	dictCache[path] = result
	dictCacheMu.Unlock()
	return result
}

// ReloadDicts clears cached dictionaries and reloads from disk.
func ReloadDicts() {
	dictCacheMu.Lock()
	dictCache = make(map[string]map[string]string)
	dictCacheMu.Unlock()
	_ = GetDict(cfg.Paths.DictAPT)
	_ = GetDict(cfg.Paths.DictCrime)
	_ = GetDict(cfg.Paths.DictNoise)
}
