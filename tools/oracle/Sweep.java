import de.vdi.vdi2770.processor.common.Message;
import de.vdi.vdi2770.processor.common.MessageLevel;
import de.vdi.vdi2770.processor.report.ContainerValidator;
import de.vdi.vdi2770.processor.report.Report;

import java.io.File;
import java.util.Locale;

/** Runs the reference implementation over each container and prints JSON.
 *  Calls ContainerValidator directly: the bundled CLI cannot parse its own
 *  -report option under commons-cli 1.6.0. */
public class Sweep {

    static String q(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"':  b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n");  break;
                case '\r': b.append("\\r");  break;
                case '\t': b.append("\\t");  break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        return b.append('"').toString();
    }

    static void emit(Report r, StringBuilder out, boolean[] first, int depth) {
        for (Message m : r.getMessages()) {
            if (!first[0]) out.append(",");
            first[0] = false;
            out.append("{\"level\":").append(q(String.valueOf(m.getLevel())))
               .append(",\"indent\":").append(m.getIndent())
               .append(",\"depth\":").append(depth)
               .append(",\"text\":").append(q(m.getText())).append("}");
        }
        for (Report sub : r.getSubReports()) emit(sub, out, first, depth + 1);
    }

    public static void main(String[] args) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < args.length; i++) {
            if (i > 0) out.append(",");
            File f = new File(args[i]);
            out.append("{\"container\":").append(q(args[i]))
               .append(",\"name\":").append(q(f.getName())).append(",\"messages\":[");
            boolean[] first = {true};
            try {
                ContainerValidator v = new ContainerValidator(Locale.US, true);
                Report r = v.validate(f, MessageLevel.INFO, true);
                emit(r, out, first, 0);
            } catch (Throwable t) {
                out.append("{\"level\":\"EXCEPTION\",\"indent\":0,\"depth\":0,\"text\":")
                   .append(q(t.getClass().getName() + ": " + t.getMessage())).append("}");
            }
            out.append("]}");
        }
        System.out.println(out.append("]"));
    }
}
