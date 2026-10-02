function fn() {
  var env = karate.env || 'local';
  var config = { baseUrl: 'http://localhost:8080' };
  if (env === 'dev') {
    // クラウドの開発環境に向けるとき: -Dkarate.env=dev -DbaseUrl=https://<your-dev-host>
    config.baseUrl = karate.properties['baseUrl'];
  }
  return config;
}
