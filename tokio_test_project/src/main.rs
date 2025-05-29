use std::thread;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut url_groups = Vec::new();
    url_groups.push("https://config.net.cn/tools/ProvinceCityCountry.html");

    for a_url in url_groups {
        println!("[TID={:?}] [INFO] start to add a spider on: {}", thread::current().id(), a_url);
        println!("[TID={:?}] before reqwest::get ({}) time: {:?}", thread::current().id(), a_url, std::time::SystemTime::now());
        let response = reqwest::get(a_url).await?;
        println!("[TID={:?}] after reqwest::get ({}) await time: {:?}", thread::current().id(), a_url, std::time::SystemTime::now());
        let html_body = response.text().await?;
        println!("[TID={:?}] got html_body, length = {} time: {:?}", thread::current().id(), html_body.len(), std::time::SystemTime::now());
        //println!("html_body = {html_body:?}");
    }

    Ok(())
}