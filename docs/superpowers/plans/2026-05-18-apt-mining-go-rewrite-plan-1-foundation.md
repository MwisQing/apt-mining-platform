# Plan 1: Go 环境搭建与基础框架

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 安装 Go + PostgreSQL，初始化 Go + Gin 项目，创建数据库迁移，实现健康检查接口。

**Architecture:** 从零搭建 Go 后端骨架。安装工具链 → 初始化 Go module → 创建目录结构 → 创建 PostgreSQL 数据库 → 执行迁移建表 → 启动 Gin 服务 → 验证健康检查。

**Tech Stack:** Go 1.22+, PostgreSQL 15+, Gin, lib/pq

**前置状态：** Go 和 PostgreSQL 均未安装。需要从安装包开始。

---

### 任务概览

| 任务 | 产出 | 预计时间 |
|---|---|---|
| Task 1: 安装 Go | `go version` 可用 | 5 min |
| Task 2: 安装 PostgreSQL | `psql` 可用，服务运行 | 10 min |
| Task 3: 初始化 Go 项目 | `backend_v2/go.mod` + 目录结构 | 5 min |
| Task 4: 数据库迁移脚本 | `migrations/001_initial.up.sql` + `down.sql` | 10 min |
| Task 5: 配置加载 | `internal/config/config.go` | 5 min |
| Task 6: 数据库连接 | `internal/db/db.go` | 5 min |
| Task 7: 健康检查接口 | `GET /api/health` 返回 JSON | 10 min |
| Task 8: 版本接口 | `GET /api/version` 返回版本信息 | 5 min |
| Task 9: 集成测试验证 | `curl` 验证所有接口 | 5 min |

---

### Task 1: 安装 Go

**Files:** 系统安装（不在项目中修改文件）

- [ ] **Step 1: 下载并安装 Go 1.22+**

使用 `winget` 安装（Windows 推荐方式）：

```bash
# 检查 winget 是否可用
winget --version
```

如果 winget 可用：
```bash
winget install --id GoLang.Go --exact
```

如果 winget 不可用，手动下载安装：
```bash
# 下载 Go 1.22 Windows 安装包
curl -LO https://go.dev/dl/go1.22.5.windows-amd64.msi
# 双击运行 .msi 安装（全部默认选项）
```

- [ ] **Step 2: 验证安装**

关闭并重新打开终端后执行：

```bash
go version
# 预期输出: go version go1.22.x windows/amd64
```

- [ ] **Step 3: 配置 Go 环境变量**

```bash
# 设置 GOPROXY（中国大陆用户推荐）
go env -w GOPROXY=https://goproxy.cn,direct
# 验证
go env GOPROXY
# 预期输出: https://goproxy.cn,direct
```

---

### Task 2: 安装 PostgreSQL

**Files:** 系统安装（不在项目中修改文件）

- [ ] **Step 1: 下载 PostgreSQL 15+**

使用 `winget` 安装：

```bash
# 使用 EDB 官方 Windows 安装包
winget install --id PostgreSQL.PostgreSQL.16 --exact
```

如果 winget 不可用，前往 https://www.enterprisedb.com/downloads/postgres-postgresql-downloads 下载 Windows x86-64 安装包。

- [ ] **Step 2: 安装配置**

安装时记录以下设置（全部使用默认值即可）：
- 端口：`5432`（默认）
- 超级用户：`postgres`
- 密码：安装时设置的密码（记下来，后面要用）

- [ ] **Step 3: 验证安装**

```bash
# 添加 PostgreSQL bin 目录到 PATH（根据实际安装路径调整）
export PATH="$PATH:/c/Program Files/PostgreSQL/16/bin"
# 验证
psql --version
# 预期输出: psql (PostgreSQL) 16.x
```

- [ ] **Step 4: 创建正式和测试数据库**

```bash
# 连接到 PostgreSQL（替换 YOUR_PASSWORD 为安装时设置的密码）
psql -U postgres

# 在 psql 中执行：
CREATE DATABASE apt_mining_prod;
CREATE DATABASE apt_mining_test;
\q
```

验证：
```bash
psql -U postgres -d apt_mining_prod -c "SELECT 1;"
# 预期输出: ?column? \n ---------- \n 1
```

---

### Task 3: 初始化 Go 项目

**Files:**
- Create: `backend_v2/` (新目录，不与旧 Python 代码冲突)
- Create: `backend_v2/go.mod`
- Create: `backend_v2/internal/` 目录结构
- Create: `backend_v2/migrations/` 目录结构
- Create: `backend_v2/config/` (复制现有配置文件)

- [ ] **Step 1: 创建目录结构**

```bash
# 在项目根目录下创建新后端目录
cd "c:/Users/Seria/Desktop/ai开发/apt-mining-platform/apt-mining-v3.3.5 修复表头筛选设备标签不显示bug"

mkdir -p backend_v2/internal/handler
mkdir -p backend_v2/internal/service
mkdir -p backend_v2/internal/model
mkdir -p backend_v2/internal/repository
mkdir -p backend_v2/internal/middleware
mkdir -p backend_v2/internal/config
mkdir -p backend_v2/internal/db
mkdir -p backend_v2/migrations
mkdir -p backend_v2/uploads
mkdir -p backend_v2/static
mkdir -p backend_v2/logs
```

- [ ] **Step 2: 初始化 Go module**

```bash
cd backend_v2
go mod init apt-mining-platform/v2
```

- [ ] **Step 3: 安装依赖**

```bash
cd backend_v2
go get -u github.com/gin-gonic/gin
go get -u github.com/lib/pq
go get -u github.com/xuri/excelize/v2
go get -u gopkg.in/yaml.v3
```

- [ ] **Step 4: 复制配置文件**

```bash
# 复制 YAML 配置文件到新后端目录
cp config/config.yaml backend_v2/config/
cp config/apt_org_dict.yaml backend_v2/config/
cp config/advanced_crime.yaml backend_v2/config/
cp config/noise_family.yaml backend_v2/config/
cp VERSION backend_v2/
```

- [ ] **Step 5: 创建 .gitignore**

```bash
cd backend_v2
cat > .gitignore << 'EOF'
*.exe
*.exe~
*.dll
*.so
*.dylib
*.test
*.out
.env
logs/*.log
uploads/*
!uploads/.gitkeep
static/*
!static/.gitkeep
data/
vendor/
EOF
touch uploads/.gitkeep static/.gitkeep
```

---

### Task 4: 数据库迁移脚本

**Files:**
- Create: `backend_v2/migrations/001_initial.up.sql`
- Create: `backend_v2/migrations/001_initial.down.sql`

- [ ] **Step 1: 创建 PostgreSQL 建表脚本**

`backend_v2/migrations/001_initial.up.sql`：

```sql
-- APT Mining Platform v2.0 数据库迁移（PostgreSQL）
-- 基于 Python v3.x 的 SQLAlchemy schema，去除快照表

-- 1. 告警表
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    device_id TEXT NOT NULL,
    first_alert_time TIMESTAMP NOT NULL,
    last_alert_time TIMESTAMP NOT NULL,
    source_ip TEXT NOT NULL,
    target TEXT NOT NULL,
    target_type TEXT,
    port TEXT,
    threat_type TEXT,
    threat_level TEXT,
    std_apt_org TEXT,
    apt_org TEXT,
    apt_org_tier TEXT,
    alert_count INTEGER,
    vendors TEXT,
    protocol TEXT,
    intel_tags TEXT,
    intel_position TEXT,
    disposal_action TEXT,
    dns_resolved_ip TEXT,
    down_traffic INTEGER,
    up_traffic INTEGER,
    asset_type TEXT,
    source_file TEXT NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    unique_hash TEXT UNIQUE,
    content_hash TEXT,
    import_id INTEGER,
    import_sheet_id INTEGER,
    import_row_id INTEGER,
    sheet_name TEXT,
    excel_row_number INTEGER,
    raw_row_hash TEXT,
    analysis_status TEXT DEFAULT '',
    is_focused INTEGER DEFAULT 0
);

-- 2. 事件主表
CREATE TABLE IF NOT EXISTS mined_events (
    id SERIAL PRIMARY KEY,
    event_name TEXT NOT NULL,
    color TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    mined_at TIMESTAMP NOT NULL,
    note TEXT
);

-- 3. 事件设备关联
CREATE TABLE IF NOT EXISTS mined_event_devices (
    event_id INTEGER REFERENCES mined_events(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    PRIMARY KEY (event_id, device_id)
);

-- 4. 事件 IOC 关联
CREATE TABLE IF NOT EXISTS mined_event_iocs (
    event_id INTEGER REFERENCES mined_events(id) ON DELETE CASCADE,
    target TEXT NOT NULL,
    port TEXT,
    PRIMARY KEY (event_id, target, port)
);

-- 5. 跟进记录
CREATE TABLE IF NOT EXISTS event_followups (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES mined_events(id) ON DELETE CASCADE NOT NULL,
    action_type TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    note TEXT
);

-- 6. 标签
CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    is_permanent INTEGER NOT NULL DEFAULT 0,
    batch_id INTEGER REFERENCES tag_batches(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL,
    note TEXT
);

-- 7. 标签批次
CREATE TABLE IF NOT EXISTS tag_batches (
    id SERIAL PRIMARY KEY,
    batch_name TEXT,
    created_at TIMESTAMP NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    device_ids_snapshot TEXT
);

-- 8. 设备标签关联
CREATE TABLE IF NOT EXISTS device_tags (
    device_id TEXT NOT NULL,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (device_id, tag_id)
);

-- 9. 追踪目标
CREATE TABLE IF NOT EXISTS traced_targets (
    id SERIAL PRIMARY KEY,
    target TEXT NOT NULL,
    port TEXT,
    traced_at TIMESTAMP,
    note TEXT,
    UNIQUE (target, port)
);

-- 10. 导入记录
CREATE TABLE IF NOT EXISTS imports (
    id SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    rows_inserted INTEGER,
    rows_skipped INTEGER,
    rows_failed INTEGER,
    total_rows INTEGER,
    parsed_rows INTEGER,
    raw_rows INTEGER,
    status TEXT,
    log TEXT,
    file_hash TEXT,
    queue_position INTEGER
);

-- 11. 导入 Sheet
CREATE TABLE IF NOT EXISTS import_sheets (
    id SERIAL PRIMARY KEY,
    import_id INTEGER REFERENCES imports(id) ON DELETE CASCADE NOT NULL,
    sheet_name TEXT NOT NULL,
    sheet_index INTEGER NOT NULL,
    header_row INTEGER,
    headers_json TEXT,
    row_count INTEGER,
    parsed_rows INTEGER,
    raw_rows INTEGER,
    failed_rows INTEGER,
    status TEXT,
    created_at TIMESTAMP NOT NULL
);

-- 12. 导入明细
CREATE TABLE IF NOT EXISTS import_rows (
    id SERIAL PRIMARY KEY,
    import_id INTEGER REFERENCES imports(id) ON DELETE CASCADE NOT NULL,
    import_sheet_id INTEGER REFERENCES import_sheets(id) ON DELETE CASCADE NOT NULL,
    source_file TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    excel_row_number INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    normalized_json TEXT,
    parse_status TEXT NOT NULL,
    parse_error TEXT,
    row_hash TEXT,
    alert_id INTEGER,
    created_at TIMESTAMP NOT NULL
);

-- 13. 审计日志
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    detail TEXT,
    created_at TIMESTAMP NOT NULL
);

-- 14. 系统配置
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- ====== 索引 ======

-- 告警表索引
CREATE INDEX IF NOT EXISTS idx_alerts_device_id ON alerts(device_id);
CREATE INDEX IF NOT EXISTS idx_alerts_source_ip ON alerts(source_ip);
CREATE INDEX IF NOT EXISTS idx_alerts_target ON alerts(target);
CREATE INDEX IF NOT EXISTS idx_alerts_first_alert_time ON alerts(first_alert_time);
CREATE INDEX IF NOT EXISTS idx_alerts_std_apt_org ON alerts(std_apt_org);
CREATE INDEX IF NOT EXISTS idx_alerts_threat_type ON alerts(threat_type);
CREATE INDEX IF NOT EXISTS idx_alerts_content_hash ON alerts(content_hash);
CREATE INDEX IF NOT EXISTS idx_alerts_import_id ON alerts(import_id);
CREATE INDEX IF NOT EXISTS idx_alerts_import_row_id ON alerts(import_row_id);
CREATE INDEX IF NOT EXISTS idx_alerts_is_focused ON alerts(is_focused);
CREATE INDEX IF NOT EXISTS idx_alerts_heat_group ON alerts(device_id, target, source_ip);

-- GIN 索引：关键词搜索（全文搜索替代 LIKE '%keyword%'）
CREATE INDEX IF NOT EXISTS idx_alerts_search ON alerts USING gin(
    to_tsvector('simple',
        COALESCE(device_id, '') || ' ' ||
        COALESCE(source_ip, '') || ' ' ||
        COALESCE(target, '') || ' ' ||
        COALESCE(threat_type, '') || ' ' ||
        COALESCE(std_apt_org, '') || ' ' ||
        COALESCE(apt_org, '')
    )
);

-- 事件相关索引
CREATE INDEX IF NOT EXISTS idx_event_followups_event_id ON event_followups(event_id);
CREATE INDEX IF NOT EXISTS idx_event_iocs_lookup ON mined_event_iocs(target, port);
CREATE INDEX IF NOT EXISTS idx_device_tags_lookup ON device_tags(device_id, tag_id);

-- 导入相关索引
CREATE INDEX IF NOT EXISTS idx_import_sheets_import_id ON import_sheets(import_id);
CREATE INDEX IF NOT EXISTS idx_import_rows_import_id ON import_rows(import_id);
CREATE INDEX IF NOT EXISTS idx_import_rows_sheet_id ON import_rows(import_sheet_id);
CREATE INDEX IF NOT EXISTS idx_import_rows_status ON import_rows(parse_status);

-- 追踪索引
CREATE INDEX IF NOT EXISTS idx_traced_target_port ON traced_targets(target, port);
```

- [ ] **Step 2: 创建回滚脚本**

`backend_v2/migrations/001_initial.down.sql`：

```sql
-- 回滚所有表（警告：会删除所有数据！）
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS import_rows CASCADE;
DROP TABLE IF EXISTS import_sheets CASCADE;
DROP TABLE IF EXISTS imports CASCADE;
DROP TABLE IF EXISTS traced_targets CASCADE;
DROP TABLE IF EXISTS device_tags CASCADE;
DROP TABLE IF EXISTS tag_batches CASCADE;
DROP TABLE IF EXISTS tags CASCADE;
DROP TABLE IF EXISTS event_followups CASCADE;
DROP TABLE IF EXISTS mined_event_iocs CASCADE;
DROP TABLE IF EXISTS mined_event_devices CASCADE;
DROP TABLE IF EXISTS mined_events CASCADE;
DROP TABLE IF EXISTS alerts CASCADE;
DROP TABLE IF EXISTS config CASCADE;
```

- [ ] **Step 3: 执行迁移脚本（验证用）**

```bash
# 执行建表（正式库）
psql -U postgres -d apt_mining_prod -f backend_v2/migrations/001_initial.up.sql

# 执行建表（测试库）
psql -U postgres -d apt_mining_test -f backend_v2/migrations/001_initial.up.sql

# 验证表数量
psql -U postgres -d apt_mining_prod -c "\dt" | wc -l
# 预期输出: 15（14张表 + 标题行）
```

---

### Task 5: 配置加载

**Files:**
- Create: `backend_v2/internal/config/config.go`
- Modify: `backend_v2/main.go`（稍后创建）

- [ ] **Step 1: 编写配置加载模块**

`backend_v2/internal/config/config.go`：

```go
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Paths struct {
		DB          string `yaml:"db"`
		UploadTmp   string `yaml:"upload_tmp"`
		DictAPT     string `yaml:"dict_apt"`
		DictCrime   string `yaml:"dict_crime"`
		DictNoise   string `yaml:"dict_noise"`
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
			MultiVendorMin   int `yaml:"multi_vendor_min"`
			LateralMinTargets int `yaml:"lateral_min_targets"`
			ScanNoiseCount   int `yaml:"scan_noise_count"`
		} `yaml:"thresholds"`
	} `yaml:"badges"`
	Server struct {
		Host          string `yaml:"host"`
		Port          int    `yaml:"port"`
		AutoOpenBrowser bool `yaml:"auto_open_browser"`
	} `yaml:"server"`
}

var (
	once    sync.Once
	cfg     *Config
	cfgOnce sync.Once
	cfgPath string
)

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

	// 环境变量覆盖（可选）
	if p := os.Getenv("APT_CONFIG_PATH"); p != "" {
		cfgPath = p
	}

	return &c, nil
}

// Get 获取全局配置（懒加载单例）
func Get() *Config {
	cfgOnce.Do(func() {
		var err error
		cfg, err = Load(cfgPath)
		if err != nil {
			panic(fmt.Sprintf("failed to load config: %v", err))
		}
	})
	return cfg
}

// Init 设置配置文件路径
func Init(path string) {
	cfgPath = path
}

// ResolvePath 将相对路径解析为绝对路径
func (c *Config) ResolvePath(p string) string {
	if filepath.IsAbs(p) {
		return p
	}
	// 相对于配置文件所在目录
	cfgDir := filepath.Dir(cfgPath)
	return filepath.Join(cfgDir, p)
}
```

---

### Task 6: 数据库连接

**Files:**
- Create: `backend_v2/internal/db/db.go`

- [ ] **Step 1: 编写数据库连接模块**

`backend_v2/internal/db/db.go`：

```go
package db

import (
	"database/sql"
	"fmt"
	"os"
	"time"

	_ "github.com/lib/pq"
	"apt-mining-platform/v2/internal/config"
)

var (
	db      *sql.DB
	dbOnce  sync.Once
)

// Connect 连接 PostgreSQL 并返回 sql.DB
func Connect(cfg *config.Config) (*sql.DB, error) {
	// 优先使用环境变量，否则从配置读取
	dbName := os.Getenv("APT_DB_NAME")
	if dbName == "" {
		dbName = "apt_mining_prod"
	}

	dbHost := os.Getenv("APT_DB_HOST")
	if dbHost == "" {
		dbHost = "127.0.0.1"
	}

	dbPort := os.Getenv("APT_DB_PORT")
	if dbPort == "" {
		dbPort = "5432"
	}

	dbUser := os.Getenv("APT_DB_USER")
	if dbUser == "" {
		dbUser = "postgres"
	}

	dbPass := os.Getenv("APT_DB_PASSWORD")
	// dbPass 可以为空（Windows 默认安装可能没有密码）

	connStr := fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		dbHost, dbPort, dbUser, dbPass, dbName,
	)

	conn, err := sql.Open("postgres", connStr)
	if err != nil {
		return nil, fmt.Errorf("open database: %w", err)
	}

	// 连接池配置
	conn.SetMaxOpenConns(20)
	conn.SetMaxIdleConns(5)
	conn.SetConnMaxLifetime(30 * time.Minute)

	// 验证连接
	if err := conn.Ping(); err != nil {
		return nil, fmt.Errorf("ping database: %w", err)
	}

	return conn, nil
}

// MustConnect 连接数据库，失败则 panic
func MustConnect(cfg *config.Config) *sql.DB {
	conn, err := Connect(cfg)
	if err != nil {
		panic(fmt.Sprintf("failed to connect to database: %v", err))
	}
	return conn
}

// RunMigrations 执行 SQL 迁移文件
func RunMigrations(db *sql.DB, migrationsDir string) error {
	// 读取迁移文件
	data, err := os.ReadFile(filepath.Join(migrationsDir, "001_initial.up.sql"))
	if err != nil {
		return fmt.Errorf("read migration: %w", err)
	}

	_, err = db.Exec(string(data))
	if err != nil {
		return fmt.Errorf("execute migration: %w", err)
	}

	return nil
}
```

修正：需要补充 `sync` 导入和 `filepath` 导入。

`backend_v2/internal/db/db.go`（修正版）：

```go
package db

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	_ "github.com/lib/pq"
	"apt-mining-platform/v2/internal/config"
)

var (
	db     *sql.DB
	dbOnce sync.Once
)

// Connect 连接 PostgreSQL 并返回 sql.DB
func Connect() (*sql.DB, error) {
	dbName := os.Getenv("APT_DB_NAME")
	if dbName == "" {
		dbName = "apt_mining_prod"
	}

	dbHost := os.Getenv("APT_DB_HOST")
	if dbHost == "" {
		dbHost = "127.0.0.1"
	}

	dbPort := os.Getenv("APT_DB_PORT")
	if dbPort == "" {
		dbPort = "5432"
	}

	dbUser := os.Getenv("APT_DB_USER")
	if dbUser == "" {
		dbUser = "postgres"
	}

	dbPass := os.Getenv("APT_DB_PASSWORD")

	connStr := fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		dbHost, dbPort, dbUser, dbPass, dbName,
	)

	conn, err := sql.Open("postgres", connStr)
	if err != nil {
		return nil, fmt.Errorf("open database: %w", err)
	}

	conn.SetMaxOpenConns(20)
	conn.SetMaxIdleConns(5)
	conn.SetConnMaxLifetime(30 * time.Minute)

	if err := conn.Ping(); err != nil {
		return nil, fmt.Errorf("ping database: %w", err)
	}

	return conn, nil
}

// MustConnect 连接数据库，失败则 panic
func MustConnect() *sql.DB {
	conn, err := Connect()
	if err != nil {
		panic(fmt.Sprintf("failed to connect to database: %v", err))
	}
	return conn
}

// RunMigrations 执行 SQL 迁移文件
func RunMigrations(db *sql.DB, migrationsDir string) error {
	data, err := os.ReadFile(filepath.Join(migrationsDir, "001_initial.up.sql"))
	if err != nil {
		return fmt.Errorf("read migration: %w", err)
	}

	_, err = db.Exec(string(data))
	if err != nil {
		return fmt.Errorf("execute migration: %w", err)
	}

	return nil
}
```

---

### Task 7: 健康检查接口

**Files:**
- Create: `backend_v2/internal/handler/health.go`
- Create: `backend_v2/main.go`

- [ ] **Step 1: 创建健康检查 handler**

`backend_v2/internal/handler/health.go`：

```go
package handler

import (
	"database/sql"
	"net/http"

	"github.com/gin-gonic/gin"
)

type HealthHandler struct {
	DB *sql.DB
}

func NewHealthHandler(db *sql.DB) *HealthHandler {
	return &HealthHandler{DB: db}
}

// Health GET /api/health
func (h *HealthHandler) Health(c *gin.Context) {
	if err := h.DB.Ping(); err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"status":  "error",
			"message": "database connection failed",
			"error":   err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":  "ok",
		"message": "APT Mining Workbench v2.0",
	})
}
```

- [ ] **Step 2: 创建 main.go 入口**

`backend_v2/main.go`：

```go
package main

import (
	"fmt"
	"log"
	"path/filepath"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/config"
	"apt-mining-platform/v2/internal/db"
	"apt-mining-platform/v2/internal/handler"
)

func main() {
	// 1. 加载配置
	configDir, _ := filepath.Abs("config")
	config.Init(filepath.Join(configDir, "config.yaml"))
	cfg := config.Get()

	log.Printf("Config loaded: host=%s port=%d", cfg.Server.Host, cfg.Server.Port)

	// 2. 连接数据库
	database := db.MustConnect()
	defer database.Close()

	log.Println("Database connected")

	// 3. 执行迁移
	migrationsDir := filepath.Join(".", "migrations")
	if err := db.RunMigrations(database, migrationsDir); err != nil {
		log.Printf("Migration warning: %v (may already be applied)", err)
	}

	log.Println("Migrations complete")

	// 4. 设置 Gin
	gin.SetMode(gin.ReleaseMode)
	r := gin.Default()

	// CORS 中间件
	r.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})

	// 静态文件服务（Vue 打包产物）
	r.Static("/static", "./static")
	r.NoRoute(func(c *gin.Context) {
		c.File("./static/index.html")
	})

	// 5. 注册路由
	healthHandler := handler.NewHealthHandler(database)

	api := r.Group("/api")
	{
		api.GET("/health", healthHandler.Health)
	}

	// 6. 启动服务
	addr := fmt.Sprintf("%s:%d", cfg.Server.Host, cfg.Server.Port)
	log.Printf("Server starting on %s", addr)
	if err := r.Run(addr); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
```

- [ ] **Step 3: 编译并验证**

```bash
cd backend_v2
go build -o apt-mining.exe .
# 预期: 无报错，生成 apt-mining.exe
```

---

### Task 8: 版本接口

**Files:**
- Modify: `backend_v2/internal/handler/health.go`（添加 Version handler）

- [ ] **Step 1: 添加版本读取逻辑**

在 `backend_v2/internal/handler/health.go` 末尾添加：

```go

type VersionHandler struct{}

func NewVersionHandler() *VersionHandler {
	return &VersionHandler{}
}

// Version GET /api/version
func (h *VersionHandler) Version(c *gin.Context) {
	// 读取 VERSION 文件
	version := "unknown"
	if data, err := os.ReadFile("../VERSION"); err == nil {
		version = strings.TrimSpace(string(data))
	}

	c.JSON(http.StatusOK, gin.H{
		"version":    version,
		"engine":     "go",
		"repository": "https://github.com/user/apt-mining-platform",
	})
}
```

修正 `health.go`，补充需要的导入。完整文件：

```go
package handler

import (
	"database/sql"
	"net/http"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
)

type HealthHandler struct {
	DB *sql.DB
}

func NewHealthHandler(db *sql.DB) *HealthHandler {
	return &HealthHandler{DB: db}
}

// Health GET /api/health
func (h *HealthHandler) Health(c *gin.Context) {
	if err := h.DB.Ping(); err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"status":  "error",
			"message": "database connection failed",
			"error":   err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":  "ok",
		"message": "APT Mining Workbench v2.0",
	})
}

type VersionHandler struct{}

func NewVersionHandler() *VersionHandler {
	return &VersionHandler{}
}

// Version GET /api/version
func (h *VersionHandler) Version(c *gin.Context) {
	version := "unknown"
	if data, err := os.ReadFile("../VERSION"); err == nil {
		version = strings.TrimSpace(string(data))
	}

	c.JSON(http.StatusOK, gin.H{
		"version":    version,
		"engine":     "go",
		"repository": "https://github.com/user/apt-mining-platform",
	})
}
```

- [ ] **Step 2: 在 main.go 中注册版本路由**

在 `main.go` 的路由注册部分，`api.GET("/health", ...)` 下面添加：

```go
versionHandler := handler.NewVersionHandler()
api.GET("/version", versionHandler.Version)
```

- [ ] **Step 3: 编译验证**

```bash
cd backend_v2
go build -o apt-mining.exe .
# 预期: 无报错
```

---

### Task 9: 集成测试验证

**Files:** 无文件修改，纯测试

- [ ] **Step 1: 设置测试数据库环境变量**

```bash
# 使用测试库运行
export APT_DB_NAME=apt_mining_test
```

- [ ] **Step 2: 启动后端服务**

```bash
cd backend_v2
./apt-mining.exe
# 日志应显示: Config loaded, Database connected, Migrations complete, Server starting
```

- [ ] **Step 3: 新开终端验证接口**

```bash
# 健康检查
curl http://127.0.0.1:8088/api/health
# 预期: {"status":"ok","message":"APT Mining Workbench v2.0"}

# 版本信息
curl http://127.0.0.1:8088/api/version
# 预期: {"version":"v3.3.5","engine":"go","repository":"..."}

# 不存在的接口（应返回 index.html fallback）
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8088/nonexistent
# 预期: 200（SPA fallback）

# CORS 预检
curl -X OPTIONS -H "Origin: http://localhost:5173" -H "Access-Control-Request-Method: GET" http://127.0.0.1:8088/api/health -v
# 预期: 204，包含 Access-Control-Allow-Origin: *
```

- [ ] **Step 4: 验证数据库表**

```bash
psql -U postgres -d apt_mining_test -c "\dt"
# 预期显示 14 张表：alerts, mined_events, mined_event_devices, event_followups,
# tags, tag_batches, device_tags, traced_targets, imports, import_sheets,
# import_rows, audit_log, config
```

- [ ] **Step 5: 提交**

```bash
cd backend_v2
git add -A
git commit -m "feat: Go foundation - environment, DB migration, health check, version API

- Install Go 1.22+ and PostgreSQL 15+
- Initialize Go module with Gin, lib/pq, excelize, yaml.v3
- Create PostgreSQL migration script (14 tables + indexes)
- Config loading from YAML with env override
- Database connection pool (max 20 conns)
- GET /api/health - database ping check
- GET /api/version - version info from VERSION file
- CORS middleware and SPA fallback routing"
```

---

## 计划自审

1. **占位符扫描：** 无 TBD/TODO。所有代码块完整。
2. **内部一致性：** `main.go` 中的 `config.Get()` 调用方式与 `config.go` 的单例模式一致。`db.MustConnect()` 不需要参数，通过环境变量控制数据库。
3. **范围检查：** 本计划仅包含环境搭建、数据库、配置、健康检查。不包含业务 API。
4. **歧义检查：** PostgreSQL 安装密码通过环境变量 `APT_DB_PASSWORD` 传递，Windows 默认安装可能无密码（空字符串）。

---

Plan 1 完成后，后端骨架应能启动并响应 `/api/health` 和 `/api/version`。后续 Plan 2 将在此基础上实现核心查询引擎。
