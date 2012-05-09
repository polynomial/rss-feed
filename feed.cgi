#!/usr/bin/perl 
# Ben Smith 5/12
# Proof of concept for a basic oauth token based rss/atom feed reader.
# TODO: cron method that allows you to update automatically, currently done with shell wrapper

use strict;
use warnings;

use Getopt::Long;

use XML::Feed;
use LWP::Simple;
use HTTP::Date;
use Getopt::Long;
use URI::Escape;
use POSIX qw/strftime/;
use LWP;
use utf8;
my $remote_addr = uri_unescape($ENV{'REMOTE_ADDR'});

# some browsers display data faster if we flush more often
$|++;

sub usage {
  die("usage: rss-bolt.pl -t token [-f feed_url]
  -t|--token token - specify the authentication token you want to use
  -f|--feed feed_url - URL to RSS feed you want to bolt from (defaults to Google News)
  -c|--count integer - only grab X from feed
  -v|--verbose - print debugging information helpful for finding feed problems
  --hide - default to user hide for the created bolts

  More information on the BO.LT API: https://dev.bo.lt/
  You can get your token from: https://bo.lt/app/settings#api-app-form\n");
}

my $app_secret="APP_SECRET";
my $app_key="APP_KEY";
my ($help, $stamp, $verbose, $hide, $batch, $token, $feedurl, $update, $account, $image, $description);
my $grab_count = 10;
my $grabbed = 0;
my $http_prefix = "http://some.url/pin/";
my $cookie_domain = "some.domain";
my $cgi_url = "http://" . $cookie_domain . "/feed.cgi";
my $http_dir = "/some/place/html/pin/";
my $log_dir = "/some/place/html/";
my $tag = "feed";
my $async = "FALSE";
my $not_really_unique_string = rand();
my $title = "Ahoy";
#$verbose = "true";
my $custom_tags = "rss=true";


sub parse_feed_url {
  my $url = $_[0];
  if ($url =~ /pinterest.com/ || $url =~ /tumblr.com/) {
    if ($url !~ /rss$/) {
      $url .= "/rss";
      $url =~ s/\/\/rss/\/rss/;
    }
  }
  return $url;
}

sub bolt_search {
  my $query = $_[0];
  my $token = $_[1];

  my $encoded_query = uri_escape($query);
  my $bolt_request = "https://api.bo.lt/search/bolt.plain?access_token=" . $token;
  if ($account) {
    $encoded_query .= uri_escape("+@" . $account);
    $bolt_request .= "&account_id=" . $account;
  }
  $bolt_request .= "&text=zbomb+" . $encoded_query;
  if ($verbose) {
    print "about to search with $bolt_request\n";
  }
  return get_url($bolt_request);
}

sub get_url {
  my $url = $_[0];
  my $user_agent = LWP::UserAgent->new;
  my $output = $user_agent->get($url);
  if ($verbose) {
    print "get_url: $url success " . $output->is_success . "and status " . $output->status_line . "\n";
  }
  if ($output->is_success) {
    return $output;
  } else {
    return "failed";
  }
}

sub put_content {
  my $filename = $_[0];
  my $data = $_[1];
  open(FH, ">$filename");
  print FH $data;
  close(FH);
}

sub bolt {
  my $url = $_[0];
  my $comment = $_[1];
  my $token = $_[2];
    
  my $bolt_request = "https://api.bo.lt/bolt/create.plain?access_token=" . $token;
  $bolt_request .= "&async=" . $async;
  if ($hide) {
    $bolt_request .= "&hide=true";
  }
  if ($account) {
    $bolt_request .= "&account_id=" . $account;
  }
  my $verbose = $_[3];
  my $content = $_[4];
  my $bolt_output = "";
  my $encoded_url = uri_escape($url);
  my $collection = "";
  if ($verbose) {
    print "INFO: inside bolt with $url $comment $token $verbose\n";
  }
  my $search_results = bolt_search($url, $token);
  if ($verbose) {
    print "INFO: search results: " . $search_results->content . "\n";
  }
  if ($search_results->content =~ /url.+?http:/) {
    if ($verbose) {
      print "INFO: already bolted $url\n";
    }
    return;
  }

  
  if ($url =~ /reddit.com/) { 
    my $content_link = "";
    my $subreddit = "";
    my $comment_link = "";
    if ($content =~ /<a href="([^"]+)">\[link\]<\/a>/) {
      $content_link = $1;
    }
    if ($content =~ /reddit.com\/r\/([^\/]+)\//) {
      $subreddit = $1;
    }
    if ($content =~ /(http:\/\/www.reddit.com\/r\/[^"]+)/) {
      $comment_link = $1;
    }
      
    $bolt_request .= "&data-reddit-comments=" . uri_escape($comment_link);
    $bolt_request .= "&data-reddit-subreddit=" . uri_escape($subreddit);
    $bolt_request .= "&data-reddit-description=" . uri_escape($content);
    $comment .= " #" . $subreddit . " " . $comment_link;
    
    if ($content_link eq $url) {
      $encoded_url = uri_escape("302 " . $content_link);
    } else {
      $encoded_url = uri_escape($content_link);
    }
    if ($verbose) { 
      print "INFO: REDDIT: from content $subreddit , $content_link , $comment_link\n";
      print "INFO: content $content\n";
    }
  } elsif ($url =~ /pinterest.com/) { 
    my $pin_source_url = "";
    my $pin_pinner = "";
    my $pin = get_url($url);
    my $pin_content = $pin->content;
    if ($pin_content =~ /og:title" content="([^"]+)/) {
      $title = $1;
    }
    if ($pin_content =~ /og:image" content="([^"]+)/) {
      $image = $1;
    }
    if ($pin_content =~ /pinterestapp:pinboard" content="http:\/\/pinterest.com\/[^\/]+\/([^\/]+)\//) {
      $collection = $1;
      $collection =~ s/[\-\_]/ /g;
      $bolt_request .= "&collection=" . $collection;
    }

    if ($pin_content =~ /og:description" content="([^"]+)/) {
      $description = $1;
    }
    if ($pin_content =~ /pinterestapp:source" content="([^"]+)/) {
      $pin_source_url = $1;
    }
    if ($pin_content =~ /pinterestapp:pinner" content="([^"]+)/) {
      $pin_pinner = $1;
    }
    if ($verbose) {
      print "INFO: PIN here with $title $image $description $pin_source_url and $url\n";
    }
    if ($pin_source_url !~ /http/) {
      $pin_source_url = $url;
    }
    my $pin_source = get_url($pin_source_url);
    $bolt_request .= "&data-source-url=" . uri_escape($pin_source_url);
    $bolt_request .= "&data-pin-url=" . uri_escape($url);
    $bolt_request .= "&data-description=" . uri_escape($description);
    $bolt_request .= "&data-title=" . uri_escape($title);
    $comment = $description;
    if ($pin_source =~ /^failed$/ || $pin_source_url =~ /flickr\.com/ || $pin_source_url =~ /google\./) {
      $encoded_url = uri_escape($url);
    } elsif ($pin_source_url =~ /\.(jpg|gif|png|jpeg|bmp)/i) {
      $encoded_url = uri_escape($pin_source);
    } else {
      my $line = "";
      my $parsed_page = "";
      my $added_og = 0;
      foreach $line (split(/\n/,$pin_source->content)) {
        if ($line =~ /<head/) {
          $parsed_page .= $line;
          $parsed_page .= "<base href=\"$pin_source_url\"/>\n";
        } elsif ($line =~ /property="og:image"/) {
          $parsed_page .= "<meta content=\"$image\" property=\"og:image\" />\n";
          $added_og = 1;
        } elsif ($line =~ /<body/) {
          if (!$added_og) {
            $parsed_page .= "<meta content=\"$image\" property=\"og:image\" />\n";
            $added_og = 1;
          }
          $parsed_page .= $line;
        } else {
          $parsed_page .= $line;
        }
      }
      $not_really_unique_string = rand();
      put_content($http_dir . $not_really_unique_string . ".html", $parsed_page);
      $encoded_url = uri_escape($http_prefix . $not_really_unique_string . ".html");
    }
  }

  $bolt_request .= "&data-feed-content-url=" . $encoded_url;
  $bolt_request .= "&url=" . $encoded_url; 
  my $encoded_feed_url = uri_escape($feedurl);
  $bolt_request .= "&data-feed-url=" . $encoded_feed_url;
  if ($custom_tags =~ /./) {
    my $encoded_custom_tags = uri_escape($custom_tags);
    $bolt_request .= "&data-feed-tag=" . $encoded_custom_tags;
  }

  if ($comment =~ /.+/) {
    my $utf8_comment = $comment;
    utf8::encode($utf8_comment);
    my $encoded_comment = uri_escape($utf8_comment);
    $bolt_request .= "&comment=" . $encoded_comment;
  }
  if ($verbose) {
    print "about to bolt with $bolt_request\n";
  }
  $bolt_output = get_url($bolt_request);
  my $bolt_content = $bolt_output->content;
  if ($verbose) {
    print "INFO: " . $bolt_content;
  } else {
    my $link = $bolt_content;
    $link =~ s/.+?bolt.short_url\s+([^\s]+).+/$1/s;
    print "$link\n";
  }

  print "<pre>bolt $bolt_content\n</pre>";
  if ($bolt_content =~ /http:\/\/bo.lt\//) {
    $grabbed++;
    if ($verbose) {
      print "grabbed: $grabbed $grab_count\n";
    }
  }
  #unlink $http_dir . $not_really_unique_string . ".html";
}

sub getNewLinksFromFeed {
  my $feed_url = $_[0];
  my $token = $_[1];
  my $verbose = $_[2];
  $feed_url = parse_feed_url($feed_url);

  my $xml = get($feed_url);
  return unless defined ($xml);
  use XML::Feed;
  my $feed = XML::Feed->parse(URI->new($feed_url))
    or die XML::Feed->errstr;
  if ($verbose) {
    print "INFO: " . $feed->title, "\n";
  }
  for my $item ($feed->entries) {
    my $title = $item->title;
    my $comment = $item->title;
    my $url = $item->link;
    my $content = $item->content->body;
    if ($verbose) {
      print "INFO: here with an item title $title comment $comment url $url and $content\n";
    }
    if (!$url) {
      if ($content =~ /.+?> uploaded <a href="([^"]+)".+/) {
        $url = $1;
      }
    }
    if ($url =~ /.+/) {
      if ($grabbed < $grab_count) {
        bolt($url, $comment, $token, $verbose, $content);
      }
    }
  }
}

if ($remote_addr) {
  my $query = uri_unescape($ENV{'QUERY_STRING'});
  my $cookie = uri_unescape($ENV{'HTTP_COOKIE'});
  if (!$token) {
    if ($cookie) {
      if ($cookie =~ /m4_token=([^;]+)/) {
        $token = $1;
      }
    }
  }
  if ($query) {
    if ($query =~ /error=(.*)/) {
      print "fatal error $1\n";
    } elsif ($query =~ /code=(.*)/) {
      my $oauth_token = "";
      my $secret_code_of_awesome = get_url("https://api.bo.lt/oauth/access_token.plain?app_key=" . $app_key . "&app_secret=" . $app_secret . "&code=" . $1);
      if ($secret_code_of_awesome->content =~ /access_token\t(.+)/) {
        $oauth_token = $1;
        print "Set-Cookie: m4_token=" . $1 . "; Domain=" . $cookie_domain . "; Expires=Sat, 05-May-2022 03:30:52 GMT; Path=/\n";
      }
      print "Location: " . $cgi_url . "\n";
      exit(0);
    } elsif ($query =~ /token=([^\&]+)/) {
      if (!$token) {
        $token = $1;
      }
    }
  }
  if (!$token) {
    my $callback_url = uri_escape($cgi_url);
    print "Location: https://bo.lt/app/dialog/oauth?app_key=" . $app_key . "&redirect_uri=" . $callback_url . "&scope=CREATE,READ,EDIT,ADMINISTER\n";
    exit(0);
  }

   
  if ($query) { 
    print "Content-Type: text/html\n\n";

    if ($query =~ /batch=([^\&]+)/) {
      $batch = $1;
    }
    if ($query =~ /tag=([^\&]+)/) {
      $custom_tags = $1;
    }
    if ($query =~ /URL=([^\&]+)/) {
      $feedurl = $1;
    }
    if ($query =~ /update=([^\&]+)/) {
      $update = $1;
    }
  
    if ($query =~ /hide=true/) {
      $hide = "--hide";
    }
  
 $verbose="true";
    $grab_count = 5;
      my $accounts = get_url("https://api.bo.lt/accounts.plain?access_token=" . $token);
      if ($accounts->content =~ /accounts:(\d+).default_for_user	true/) {
        my $account_id = $1;
        if ($accounts->content =~ /accounts:$account_id.id	(\S+)/) {
          $account = $1;
        }
      }
      if ($verbose) {
        print "INFO:accounts: " . $accounts->content . "\n";
      }
    if ($update =~ /update/ || $batch =~ /true/) {
      if ($account =~ /./) {
        if ($verbose) {
          print "about to save with $account $token $feedurl $custom_tags\n";
        }
        open(FH,">>" . $log_dir . "/batch-account");
        print FH "$token $account $feedurl $custom_tags $hide\n";
        close(FH);
      }
    }
    print "<pre>Working on feed: " . $feedurl . " with custom_tags: " . $custom_tags . "\n</pre>";
  } else {
    print "Content-Type: text/html\n\n";
    print "<body><html>
      <form name=\"input\" action=\"feed.cgi\" method=\"get\">
        URL: <input type=\"text\" name=\"URL\" />
        token: <input type=\"text\" name=\"token\"";
    if ($token) {
      print " value=\"" . $token . "\"";
    }
    print " />
        tags: <input type=\"text\" name=\"tag\" />
        <input type=\"checkbox\" name=\"update\" value=\"update\" /> autobolt
        <input type=\"checkbox\" name=\"hide\" value=\"true\" /> hide
        <input type=\"checkbox\" name=\"batch\" value=\"true\" /> batch
        <input type=\"submit\" value=\"Submit\" />
      </form>
      <br><a href=\"/reset.cgi\">Reset token/login to another account</a><br>
      </html></body>";
     exit(0);
   }
} else {
  GetOptions(
    "account|a=s" => \$account,
    "feed|f=s" => \$feedurl,
    "hide" => \$hide,
    "token|t=s" => \$token,
    "tags=s" => \$custom_tags,
    "verbose|v" => \$verbose,
    "help|h" => \$help,
    "count|c=s" => \$grab_count,
  );
}

if ($feedurl) {
  if ($feedurl !~ /^http/) {
    $feedurl = "http://" . $feedurl;
  }
  if ($feedurl =~ /pinterest.com/ || $feedurl =~ /tumblr.com/) {
    if ($feedurl =~ /pinterest.com\/([^\/]+)\/*$/) {
      my $pinner = $1;
      my $pin_account = get_url($feedurl);
      my $line = "";
      foreach $line (split(/\n/,$pin_account->content)) {
        if ($line =~ /<h3 class="serif"><a href="\/$pinner\/([^"]+)"/) {
          my $pinboard = "http://pinterest.com/$pinner/$1";
          print "<pre>found pinboard $pinboard pinner $pinner\n</pre>";
          getNewLinksFromFeed($pinboard, $token, $verbose);
          $grabbed = 0;
        }
      }
    }
  }
}

if ($verbose) {
  print "INFO: feed url is now $feedurl\n";
}

if (!$token) {
  print "ERROR: Need to specify an access token (from https://bo.lt/app/settings#api-app-form)\n";
  usage();
}

if ($help) {
  usage();
}

getNewLinksFromFeed($feedurl, $token, $verbose);
