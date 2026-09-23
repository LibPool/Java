# Java 库索引

本目录收录来自 Maven Central 的 Java 库索引，按 Java 大版本与 Maven groupId 包路径组织：

- 大版本目录：`java-v8`、`java-v11`、`java-v17`、`java-v21`、`java-v25`、`java-v26`
- 包路径：`groupId` 中的 `.` 转成目录分隔符，例如 `org.springframework:spring-context` 位于 `org/springframework/spring-context.md`
- 库若兼容多个 Java 大版本，会同时出现在所有后续版本目录中

当前共收录 15299 个 Maven 坐标（来源为 Maven Central 搜索翻页与人工种子）：

- java-v8：6317 个库
- java-v11：6820 个库
- java-v17：8203 个库
- java-v21：8416 个库
- java-v25：8430 个库
- java-v26：8434 个库

## 数据源

- Maven Central：https://repo.maven.apache.org/maven2/
- Maven Central 搜索：https://search.maven.org/
- 中央仓库主页：https://central.sonatype.com/

## 生成方式

```bash
python tools/generate_index.py --crawl --crawl-limit 15000 --workers 24
```

种子坐标清单见 [tools/seeds/java.json](tools/seeds/java.json)。
