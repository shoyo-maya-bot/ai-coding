package karate;

import com.intuit.karate.junit5.Karate;
import org.junit.jupiter.api.Tag;

/**
 * API テスト（Karate）. アプリと DB を起動してから実行する.
 *
 * <pre>
 *   ./gradlew bootRun --args='--spring.profiles.active=local'   # 別のターミナルで
 *   ./gradlew karateTest
 * </pre>
 */
@Tag("karate")
class ApiKarateTest {

    @Karate.Test
    Karate members() {
        return Karate.run("classpath:karate/members.feature");
    }
}
