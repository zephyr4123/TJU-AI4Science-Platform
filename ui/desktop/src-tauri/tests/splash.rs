//! 启动页的几条规矩，扫源码查（每个检查器带一条反例，证明它抓得到）：
//! - 标与页面的 favicon 是同三条路径（品牌标只有一份，外层 #261）；
//! - 外壳给的字只用 `textContent` 放上去，不拼 HTML（后端起不来时的原因里可能带着输出原文）；
//! - 只用本地的东西：没有内联脚本（CSP 只放行 'self'）、不引外面的地址。

use std::path::Path;

fn read(relative: &str) -> String {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(relative);
    std::fs::read_to_string(&path)
        .unwrap_or_else(|error| panic!("读不了 {}：{error}", path.display()))
}

fn mark_paths(svg: &str) -> Vec<String> {
    svg.split("<path")
        .skip(1)
        .filter_map(|tag| {
            let start = tag.find(" d=\"")? + 4;
            Some(tag[start..start + tag[start..].find('"')?].to_string())
        })
        .collect()
}

/// 把字当 HTML 塞进页面的写法
fn writes_html(js: &str) -> Vec<&'static str> {
    [
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "createContextualFragment",
    ]
    .into_iter()
    .filter(|sink| js.contains(sink))
    .collect()
}

/// 本地页里不该有的：内联脚本、外面的地址
fn leaves_home(html: &str) -> Vec<&'static str> {
    let mut found = Vec::new();
    let tags = html
        .split("<script")
        .skip(1)
        .map(|rest| &rest[..rest.find('>').unwrap_or(rest.len())]);
    if tags.into_iter().any(|attrs| !attrs.contains("src=")) {
        found.push("内联脚本");
    }
    if html.contains("http://") || html.contains("https://") || html.contains("src=\"//") {
        found.push("外面的地址");
    }
    found
}

#[test]
fn the_splash_draws_the_same_mark_as_the_page() {
    let splash = mark_paths(&read("../splash/index.html"));
    let favicon = mark_paths(&read("../../web/public/favicon.svg"));
    assert_eq!(favicon.len(), 3);
    assert_eq!(splash, favicon);
    let redrawn = r#"<path class="a" d="M0 0Z"/><path d="M1 1Z"/><path d="M2 2Z"/>"#;
    assert_ne!(mark_paths(redrawn), favicon, "反例：画走样的标要被认出来");
}

#[test]
fn the_splash_only_ever_sets_text() {
    assert_eq!(
        writes_html(&read("../splash/splash.js")),
        Vec::<&str>::new()
    );
    assert_eq!(
        writes_html("el.innerHTML = problem.text"),
        ["innerHTML"],
        "反例"
    );
}

#[test]
fn the_splash_is_all_local() {
    for file in ["../splash/index.html", "../splash/splash.css"] {
        assert_eq!(leaves_home(&read(file)), Vec::<&str>::new(), "{file}");
    }
    let fine = r#"<script type="module" src="splash.js"></script>"#;
    assert_eq!(leaves_home(fine), Vec::<&str>::new());
    let bad = r#"<script type="module">alert(1)</script><link href="https://fonts.example/x.css">"#;
    assert_eq!(leaves_home(bad), ["内联脚本", "外面的地址"], "反例");
}

/// 带这个 id 的那个开标签
fn opening<'a>(html: &'a str, id: &str) -> &'a str {
    let at = html.find(&format!("id=\"{id}\"")).expect("有这个 id");
    let start = html[..at].rfind('<').unwrap();
    let end = at + html[at..].find('>').unwrap();
    &html[start..=end]
}

#[test]
fn screen_readers_hear_the_steps_not_the_clock() {
    let html = read("../splash/index.html");
    assert!(opening(&html, "status").contains(r#"aria-live="polite""#));
    assert!(
        opening(&html, "elapsed").contains(r#"aria-hidden="true""#),
        "每秒一跳的表不念"
    );
    assert!(
        opening(&html, "rows").contains(r#"aria-live="polite""#),
        "新的一步要念"
    );
    let js = read("../splash/splash.js");
    assert!(!js.contains("${error}"), "外壳的原话不上屏");
}
