# app のコンテナイメージの例（ECS Fargate の API・バッチ用. dev-environment の cloud/README.md の「コンテナイメージの例」）.
#
#   ./gradlew bootJar
#   docker build -t app:0.1.0 .
#
# 大事な点: ENTRYPOINT を java -jar（exec 形式）にし、CMD は書かない（空）.
# バッチのジョブフロー（dev-environment の cloud/modules/batch-workflow）は、ECS のコンテナの上書きで Command に
# ["--app.batch.job=JOB0001", "--input=s3://…"] を渡す. ECS の Command は Docker の CMD を置き換えるので、
# ENTRYPOINT が java -jar のときだけ、これが Spring Boot の起動引数として後ろに付く.
# ENTRYPOINT を書かずに CMD ["java", "-jar", …] にすると、Command で起動のコマンドごと置き換わり、
# 「--app.batch.job=JOB0001」を実行しようとしてタスクが起動しない.
#
# 本番で使うときは、ベースイメージをダイジェスト（@sha256:…）で固定し、脆弱性検査（trivy image など）を通してください.
FROM amazoncorretto:17-al2023-headless

ARG JAR_FILE=build/libs/app-0.1.0.jar
WORKDIR /opt/app
COPY ${JAR_FILE} /opt/app/app.jar

# root で動かさない（ユーザーを作らずに番号で指定する）
USER 10001:10001

# API は 8080 番（application.yml の server.port）. バッチは待ち受けない
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
