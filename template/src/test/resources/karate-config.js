function fn() {
  var env = karate.env || 'local';
  // -DbaseUrl があればそれを使う（build.gradle の karateTest がテストの JVM に渡す）
  var baseUrl = karate.properties['baseUrl'];
  if (!baseUrl) {
    if (env !== 'local') {
      // クラウドの開発環境などに向けるとき: -Dkarate.env=dev -DbaseUrl=https://<your-dev-host>
      karate.fail('karate.env=' + env + ' では -DbaseUrl の指定が必要です');
    }
    baseUrl = 'http://localhost:8080';
  }
  karate.log('karate.env =', env, ', baseUrl =', baseUrl);
  return { baseUrl: baseUrl };
}
